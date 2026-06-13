"""Always-on microphone with Silero VAD.

A single InputStream feeds a VAD thread that segments speech into utterances.
Two consumers use it:

  - the conversation loop pulls finalised utterances via `utterances()`
  - barge-in fires the instant VAD crosses into speech, via `on_speech_start`

16 kHz mono, 512-sample (32 ms) frames -- the size Silero expects. PipeWire
resamples from the headset's native rate, so we just ask for 16 kHz directly.
"""
from __future__ import annotations

import queue
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort
import sounddevice as sd

SAMPLE_RATE = 16_000
FRAME = 512                       # samples -> 32 ms at 16 kHz
FRAME_MS = FRAME / SAMPLE_RATE * 1000
VAD_MODEL = Path(__file__).parent / "models" / "silero_vad_v6.onnx"
CONTEXT = 64                      # samples of previous frame the v6 model wants


class SileroVAD:
    """Silero VAD v6 via onnxruntime -- avoids a multi-GB torch dependency.

    Stateful: feed one 512-sample frame at a time. The model takes 576 samples
    (64 of trailing context from the previous frame + the 512 new ones) plus
    the LSTM h/c states, all of which carry across frames.
    """

    def __init__(self, path: Path = VAD_MODEL):
        self._sess = ort.InferenceSession(
            str(path), providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self):
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._ctx = np.zeros(CONTEXT, dtype=np.float32)

    def __call__(self, frame: np.ndarray, sr: int = SAMPLE_RATE) -> float:
        frame = frame.astype(np.float32)
        win = np.concatenate([self._ctx, frame]).reshape(1, -1)
        prob, self._h, self._c = self._sess.run(
            None, {"input": win, "h": self._h, "c": self._c})
        self._ctx = frame[-CONTEXT:]
        return float(np.ravel(prob)[0])


@dataclass
class VadConfig:
    threshold: float = 0.5        # speech probability to count a frame as speech
    silence_ms: int = 800         # trailing silence that ends an utterance
    min_speech_ms: int = 200      # drop blips shorter than this
    preroll_ms: int = 300         # audio kept before onset so we don't clip starts
    start_frames: int = 3         # consecutive speech frames before "speech started"


def _resample(x: np.ndarray, n_out: int) -> np.ndarray:
    """Linear resample to n_out samples -- fine for 48k/44.1k -> 16k speech."""
    if len(x) == n_out:
        return x
    idx = np.linspace(0, len(x) - 1, n_out)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


class Mic:
    def __init__(self, cfg: VadConfig | None = None, device=None, rate=None,
                 channels=None, channel=0):
        self.cfg = cfg or VadConfig()
        self.device = device
        # Some interfaces (e.g. the Scarlett via PipeWire) only present the mic
        # when opened as stereo -- you read channel 0. Default to opening every
        # input channel the device has and selecting `channel`.
        if channels is None:
            try:
                channels = int(sd.query_devices(device, "input")["max_input_channels"])
            except Exception:
                channels = 1
        self.channels = max(1, channels)
        self.channel = min(channel, self.channels - 1)
        # Many interfaces (e.g. the Scarlett) only run at 48 kHz. Capture at the
        # device's native rate and downsample each block to 16 kHz for VAD/STT.
        if rate is None:
            try:
                rate = int(sd.query_devices(device, "input")["default_samplerate"])
            except Exception:
                rate = SAMPLE_RATE
        self.capture_rate = rate
        self.cap_block = round(FRAME * rate / SAMPLE_RATE)
        self._model = SileroVAD()
        self._raw: queue.Queue[np.ndarray] = queue.Queue()
        self._utterances: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        # set while we believe the user is mid-utterance; barge-in reads this
        self.speaking = threading.Event()
        # optional callback fired once when speech onset is confirmed
        self.on_speech_start = None
        # raised to make the VAD ignore the mic (e.g. while the bot talks and
        # we don't trust echo isolation); left clear for headset use
        self.muted = threading.Event()

    # -- stream plumbing ----------------------------------------------------
    def _callback(self, indata, frames, t, status):  # noqa: ARG002
        frame = indata[:, self.channel].copy()
        if self.capture_rate != SAMPLE_RATE:
            frame = _resample(frame, FRAME)
        self._raw.put(frame)

    def start(self):
        if self._running:
            return
        self._running = True
        self._stream = sd.InputStream(
            samplerate=self.capture_rate, channels=self.channels, dtype="float32",
            blocksize=self.cap_block, device=self.device, callback=self._callback,
        )
        self._stream.start()
        self._thread = threading.Thread(target=self._vad_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    # -- the VAD segmenter --------------------------------------------------
    def _vad_loop(self):
        cfg = self.cfg
        preroll = deque(maxlen=int(cfg.preroll_ms / FRAME_MS))
        buf: list[np.ndarray] = []
        in_speech = False
        speech_run = 0
        silence_run = 0
        silence_limit = int(cfg.silence_ms / FRAME_MS)

        while self._running:
            try:
                frame = self._raw.get(timeout=0.5)
            except queue.Empty:
                continue
            if self.muted.is_set():
                preroll.clear(); buf.clear(); in_speech = False
                speech_run = silence_run = 0
                self.speaking.clear()
                continue

            prob = self._model(frame, SAMPLE_RATE)
            voiced = prob >= cfg.threshold

            if not in_speech:
                preroll.append(frame)
                speech_run = speech_run + 1 if voiced else 0
                if speech_run >= cfg.start_frames:
                    in_speech = True
                    silence_run = 0
                    buf = list(preroll)
                    preroll.clear()
                    self.speaking.set()
                    if self.on_speech_start:
                        try:
                            self.on_speech_start()
                        except Exception:
                            pass
            else:
                buf.append(frame)
                silence_run = 0 if voiced else silence_run + 1
                if silence_run >= silence_limit:
                    self.speaking.clear()
                    audio = np.concatenate(buf)
                    dur_ms = len(audio) / SAMPLE_RATE * 1000
                    speech_ms = dur_ms - cfg.silence_ms
                    if speech_ms >= cfg.min_speech_ms:
                        self._utterances.put(audio)
                    buf = []
                    in_speech = False
                    speech_run = 0

    # -- consumer API -------------------------------------------------------
    def utterances(self):
        """Yield finalised utterances (float32 mono @ 16 kHz) forever."""
        while True:
            yield self._utterances.get()

    def next_utterance(self, timeout=None) -> np.ndarray | None:
        try:
            return self._utterances.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self):
        """Discard any buffered utterances (e.g. after a barge-in)."""
        try:
            while True:
                self._utterances.get_nowait()
        except queue.Empty:
            pass


if __name__ == "__main__":
    # Smoke test: print VAD onsets and utterance durations as you talk.
    m = Mic()
    m.on_speech_start = lambda: print("  <speech>", end="", flush=True)
    m.start()
    print("Listening (Ctrl-C to stop). Say something...")
    try:
        for u in m.utterances():
            print(f"  utterance {len(u)/SAMPLE_RATE:.1f}s")
    except KeyboardInterrupt:
        m.stop()

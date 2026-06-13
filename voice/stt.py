"""Speech-to-text via faster-whisper.

CPU int8 by default -- small.en runs near real time on the 7800X3D and needs no
ROCm. Swap MODEL to large-v3-turbo (or point at whisper.cpp-Vulkan) if latency
ever demands the GPU.
"""
from __future__ import annotations

import numpy as np
from faster_whisper import WhisperModel

MODEL = "small.en"


class Transcriber:
    def __init__(self, model: str = MODEL, device: str = "cpu",
                 compute_type: str = "int8"):
        self.model = WhisperModel(model, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray) -> str:
        # faster-whisper wants float32 mono @ 16 kHz, which is what Mic yields.
        segments, _ = self.model.transcribe(
            audio, language="en", beam_size=1, vad_filter=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()


if __name__ == "__main__":
    from mic import SAMPLE_RATE, Mic

    t = Transcriber()
    m = Mic()
    m.start()
    print("Speak -- transcripts print below (Ctrl-C to stop).")
    try:
        for u in m.utterances():
            text = t.transcribe(u)
            if text:
                print(f"> {text}   ({len(u)/SAMPLE_RATE:.1f}s)")
    except KeyboardInterrupt:
        m.stop()

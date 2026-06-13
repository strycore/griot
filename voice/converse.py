"""Interruptible voice conversation: mic -> STT -> brain -> griot TTS.

  python converse.py --brain echo                 # plumbing/barge-in test
  python converse.py --brain claude --voice Bishop.wav --system ~/.../maestro/CLAUDE.md

Barge-in: a single always-on mic+VAD engine both segments your turns and, the
instant it hears you start talking while the bot is speaking, cuts the bot off
(`Speaker.stop()`). Closed headset / echo-cancelled source assumed; on open
speakers without AEC pass --no-barge-in (mic is muted while the bot talks).

Optional companions:
  --face-sock PATH   stream state to the iced face window (emoji + subtitles)
  --srt-dir DIR      log the conversation as a timestamped .srt subtitle file
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

import sounddevice as sd

from brain import BRAINS
from face import Face, split_emoji
from mic import SAMPLE_RATE, Mic, VadConfig
from srt import SrtLog
from stt import Transcriber
from tts import Speaker

# Appended to the persona: replies are heard, not read.
SPOKEN_STYLE = (
    "\n\nYour replies are spoken aloud through a voice synthesizer and shown as "
    "subtitles. Keep them short, plain and conversational — usually a sentence or "
    "two, no markdown or lists. You may begin a reply with a single emoji to set "
    "your on-screen expression; it is displayed on your face, not spoken."
)
BOT_NAME = "maestro"
IDLE_EMOJI = "🤖"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", default="echo", choices=list(BRAINS))
    ap.add_argument("--voice", default="Emily.wav", help="griot voice file")
    ap.add_argument("--model", default="small.en", help="faster-whisper model")
    ap.add_argument("--system", help="file with a system prompt (claude brain)")
    ap.add_argument("--brain-model", help="model for the claude brain "
                    "(e.g. haiku, sonnet) — faster pace than the default")
    ap.add_argument("--device", help="input device (name or index); default=system")
    ap.add_argument("--channel", type=int, default=0,
                    help="which input channel holds the mic (Scarlett XLR = 0)")
    ap.add_argument("--no-barge-in", action="store_true",
                    help="don't interrupt on speech; mute mic while bot talks")
    ap.add_argument("--echo-input", action="store_true",
                    help="play back the raw recording, then speak the transcript, "
                         "before the brain replies (mic/STT confirmation)")
    ap.add_argument("--face-sock", help="unix socket of the iced face window")
    ap.add_argument("--srt-dir", help="log the conversation as .srt here")
    ap.add_argument("--greeting", default="I'm listening.")
    args = ap.parse_args()

    # Stop the global cc-speak hook from double-speaking when our claude brain
    # spawns `claude -p` (its Stop hook would fire too).
    os.environ["GRIOT_VOICE_LOOP"] = "1"

    system = Path(args.system).read_text() if args.system else ""
    if args.brain == "claude":
        system = (system + SPOKEN_STYLE).strip()
    brain = BRAINS[args.brain](system=system or None, model=args.brain_model)
    device = args.device
    if device and device.isdigit():
        device = int(device)

    face = Face(args.face_sock)
    srt = SrtLog(args.srt_dir) if args.srt_dir else None

    print("loading models...", flush=True)
    stt = Transcriber(model=args.model)
    speaker = Speaker(voice=args.voice)
    mic = Mic(VadConfig(), device=device, channel=args.channel)

    # barge-in: VAD onset cuts the bot off. Only act while actually speaking.
    bot_speaking = threading.Event()

    def on_onset():
        if not args.no_barge_in and bot_speaking.is_set():
            speaker.stop()

    mic.on_speech_start = on_onset
    mic.start()

    def say(text: str) -> bool:
        """Speak one chunk; return True if interrupted by barge-in."""
        bot_speaking.set()
        if args.no_barge_in:
            mic.muted.set()        # ignore our own voice
        try:
            return speaker.speak(text)
        finally:
            bot_speaking.clear()
            if args.no_barge_in:
                mic.muted.clear()
                mic.drain()

    def play_raw(audio):
        """Play back the raw captured PCM (mic confirmation)."""
        bot_speaking.set()
        if args.no_barge_in:
            mic.muted.set()
        try:
            sd.play(audio, SAMPLE_RATE)
            sd.wait()
        finally:
            bot_speaking.clear()
            if args.no_barge_in:
                mic.muted.clear()
                mic.drain()

    print(f"[{args.brain}] voice={args.voice}  barge-in={not args.no_barge_in}"
          f"  echo-input={args.echo_input}  face={bool(args.face_sock)}"
          f"  srt={bool(args.srt_dir)}")
    face.busy(False)
    face.emoji(IDLE_EMOJI)
    if args.greeting:
        face.saying(args.greeting)
        if srt:
            srt.add(BOT_NAME, args.greeting)
        say(args.greeting)

    try:
        for utt in mic.utterances():
            text = stt.transcribe(utt)
            if not text:
                continue
            print(f"\nyou> {text}")
            face.heard(text)
            if srt:
                srt.add("you", text)
            if args.echo_input:
                print("  (playing back your audio, then the transcript)")
                play_raw(utt)
                say(f"I heard: {text}")

            face.busy(True)          # thinking
            interrupted = False
            first = True
            for chunk in brain(text):
                clean, emoji = split_emoji(chunk)
                if first:
                    face.busy(False)  # now speaking, show expression
                    first = False
                if emoji:
                    face.emoji(emoji)
                if not clean:
                    continue
                print(f"bot> {clean}")
                face.saying(clean)
                if srt:
                    srt.add(BOT_NAME, clean)
                if say(clean):
                    print("  (interrupted)")
                    interrupted = True
                    break
            face.busy(False)
            if interrupted:
                # the interrupting speech is mid-capture; it becomes the next turn
                continue
    except KeyboardInterrupt:
        pass
    finally:
        speaker.stop()
        mic.stop()
        if srt:
            srt.close()
            print(f"transcript: {srt.path}")
        print("\nbye.")


if __name__ == "__main__":
    sys.exit(main())

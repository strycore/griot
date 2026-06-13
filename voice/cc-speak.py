#!/usr/bin/env python3
"""Claude Code -> griot TTS bridge (a Stop-hook script).

Claude Code has no native voice output, but its `Stop` hook fires when a turn
finishes and hands us the transcript path. We pull the last assistant message,
strip it down to something worth hearing, and speak it through the local griot
server -- pairing with Claude Code's native `/voice` input for a fully voiced CLI.

Wire it up in settings.json:

  "hooks": { "Stop": [ { "hooks": [ {
    "type": "command",
    "command": "python3 ~/Projects/griot/voice/cc-speak.py"
  } ] } ] }

Env: CC_VOICE (griot voice, default Emily.wav), CC_TTS_HOST (default :8004),
     CC_MAX_CHARS (cap spoken length, default 700).
Reads hook JSON on stdin, returns immediately; playback runs detached so Claude
isn't blocked. A new turn cuts off the previous utterance.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

HOST = os.environ.get("CC_TTS_HOST", "http://localhost:8004")
VOICE = os.environ.get("CC_VOICE", "Emily.wav")
MAX_CHARS = int(os.environ.get("CC_MAX_CHARS", "700"))
PIDFILE = Path("/tmp/cc-speak.pid")

FENCE = re.compile(r"```.*?```", re.S)            # code blocks -> drop
INLINE = re.compile(r"`([^`]*)`")                  # inline code -> bare text
LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")        # [text](url) -> text
MD = re.compile(r"[*_#>]+")                          # emphasis/headers/quotes
LIST = re.compile(r"^\s*[-*+]\s+", re.M)            # bullet markers
PATHY = re.compile(r"\S+/\S+")                       # file paths -> skip-ish


def last_assistant_text(transcript_path: str) -> str | None:
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") != "assistant":
            continue
        content = obj.get("message", {}).get("content", [])
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        text = " ".join(p for p in parts if p).strip()
        if text:
            return text
    return None


def clean_for_speech(text: str) -> str:
    text = FENCE.sub(" ", text)
    text = LINK.sub(r"\1", text)
    text = INLINE.sub(r"\1", text)
    text = LIST.sub("", text)
    text = MD.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_CHARS:
        # cut at the last sentence boundary within the cap
        cut = text[:MAX_CHARS]
        m = list(re.finditer(r"[.!?](\s|$)", cut))
        text = cut[: m[-1].end()].strip() if m else cut.rstrip() + "..."
    return text


def stop_previous():
    try:
        pid = int(PIDFILE.read_text())
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, ValueError, ProcessLookupError):
        pass


def speak(text: str):
    req = json.dumps({"text": text, "voice_mode": "predefined",
                      "predefined_voice_id": VOICE, "stream": True})
    pipeline = (f'curl -fsSN {HOST}/tts -H "Content-Type: application/json" '
                f'-d @- | aplay -q - 2>/dev/null')
    proc = subprocess.Popen(["bash", "-c", pipeline], stdin=subprocess.PIPE,
                            start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.stdin.write(req.encode())
    proc.stdin.close()
    PIDFILE.write_text(str(proc.pid))


def main():
    # The voice loop's brain spawns `claude -p`, which would fire this same Stop
    # hook and double-speak. The loop sets GRIOT_VOICE_LOOP so we no-op there.
    if os.environ.get("GRIOT_VOICE_LOOP"):
        return 0
    try:
        hook = json.load(sys.stdin)
    except ValueError:
        return 0
    text = last_assistant_text(hook.get("transcript_path", ""))
    if not text:
        return 0
    spoken = clean_for_speech(text)
    if not spoken:
        return 0
    stop_previous()
    speak(spoken)
    return 0


if __name__ == "__main__":
    sys.exit(main())

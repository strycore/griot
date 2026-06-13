"""Interruptible speech out via griot.

Streams griot's /tts WAV into `aplay` so playback starts on the first chunk, and
exposes `stop()` so a barge-in can cut the bot off mid-sentence. `speak()` blocks
until the line finishes or is interrupted, returning True if it was interrupted.
"""
from __future__ import annotations

import subprocess
import threading

import requests

HOST = "http://localhost:8004"


class Speaker:
    def __init__(self, voice: str = "Emily.wav", host: str = HOST,
                 style: dict | None = None):
        self.voice = voice
        self.host = host
        self.style = style or {}
        self._proc: subprocess.Popen | None = None
        self._resp: requests.Response | None = None
        self._interrupt = threading.Event()
        self._lock = threading.Lock()

    def speak(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        self._interrupt.clear()
        req = {"text": text, "voice_mode": "predefined",
               "predefined_voice_id": self.voice, "stream": True, **self.style}
        with self._lock:
            self._proc = subprocess.Popen(
                ["aplay", "-q", "-"], stdin=subprocess.PIPE,
                stderr=subprocess.DEVNULL)
        try:
            self._resp = requests.post(f"{self.host}/tts", json=req, stream=True,
                                       timeout=(5, 60))
            self._resp.raise_for_status()
            for chunk in self._resp.iter_content(chunk_size=4096):
                if self._interrupt.is_set():
                    break
                if chunk and self._proc and self._proc.stdin:
                    try:
                        self._proc.stdin.write(chunk)
                    except BrokenPipeError:
                        break
        finally:
            self._close()
        return self._interrupt.is_set()

    def stop(self):
        """Cut playback now (called from the barge-in thread)."""
        self._interrupt.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.kill()

    def _close(self):
        with self._lock:
            if self._resp is not None:
                self._resp.close()
                self._resp = None
            if self._proc is not None:
                try:
                    if self._proc.stdin:
                        self._proc.stdin.close()
                except BrokenPipeError:
                    pass
                if self._interrupt.is_set() and self._proc.poll() is None:
                    self._proc.kill()
                self._proc.wait()
                self._proc = None


if __name__ == "__main__":
    import sys
    Speaker().speak(" ".join(sys.argv[1:]) or "Griot speaker test, one two three.")

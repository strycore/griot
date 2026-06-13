"""Log a voice conversation as an .srt subtitle file, written incrementally.

Each turn becomes a cue stamped from session start. End time is the next cue's
start if known, else an estimate from the text length, so the file is valid and
playable even while the conversation is still going.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path


def _ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


class SrtLog:
    def __init__(self, directory: str, now: float | None = None):
        self.dir = Path(directory).expanduser()
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.path = self.dir / f"{stamp}.srt"
        self._t0 = now if now is not None else time.time()
        self._n = 0
        self._pending: tuple[float, str] | None = None  # (start, text) not yet ended

    def add(self, speaker: str, text: str):
        text = text.strip()
        if not text:
            return
        start = time.time() - self._t0
        # close the previous cue at this cue's start
        self._flush(end=start)
        self._pending = (start, f"{speaker}: {text}")

    def _flush(self, end: float | None = None):
        if self._pending is None:
            return
        start, line = self._pending
        if end is None:
            words = max(1, len(line.split()))
            end = start + min(8.0, max(1.5, words * 0.45))
        self._n += 1
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"{self._n}\n{_ts(start)} --> {_ts(end)}\n{line}\n\n")
        self._pending = None

    def close(self):
        self._flush()

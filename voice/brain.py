"""Pluggable brains: turn a user transcript into a reply.

Each brain is a callable taking the transcript and yielding reply text in
speakable chunks (sentences) so the loop can start talking before the whole
reply is ready -- and so a barge-in can stop it between chunks.

  echo   -- repeat what was heard; for testing latency and barge-in
  claude -- the maestro persona via the claude CLI in headless mode
"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator

_SENT = re.compile(r".+?(?:[.!?]+(?:\s|$)|\n+|$)", re.S)


def split_sentences(text: str) -> list[str]:
    return [m.group().strip() for m in _SENT.finditer(text) if m.group().strip()]


def echo_brain(text: str) -> Iterator[str]:
    yield f"You said: {text}"


def claude_brain(system: str | None = None):
    """Headless `claude -p`, continuing the conversation across turns.

    Streams stdout, yielding complete sentences as they arrive so TTS can start
    early. Requires the `claude` CLI on PATH.
    """
    def run(text: str) -> Iterator[str]:
        cmd = ["claude", "-p", "--continue", "--output-format", "text"]
        if system:
            cmd += ["--append-system-prompt", system]
        cmd.append(text)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True,
                                bufsize=1)
        buf = ""
        assert proc.stdout
        for line in proc.stdout:
            buf += line
            sents = split_sentences(buf)
            # keep the last (possibly incomplete) sentence in the buffer
            if len(sents) > 1:
                for s in sents[:-1]:
                    yield s
                buf = sents[-1]
        proc.wait()
        if buf.strip():
            yield buf.strip()
    return run


BRAINS = {
    "echo": lambda **_: echo_brain,
    "claude": lambda system=None, **_: claude_brain(system),
}

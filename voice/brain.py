"""Pluggable brains: turn a user transcript into a reply.

Each brain is a callable taking the transcript and yielding reply text in
speakable chunks (sentences) so the loop can start talking before the whole
reply is ready -- and so a barge-in can stop it between chunks.

  echo    -- repeat what was heard; for testing latency and barge-in
  command -- hand the transcript to any external program and speak its stdout

griot does no inference of its own: `command` is the seam where an assistant
plugs in. The program gets the transcript as its last argument and prints the
reply; anything that can do that -- an LLM CLI, an orchestrator, a shell
script -- can be the voice loop's brain.
"""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
from collections.abc import Iterator

_SENT = re.compile(r".+?(?:[.!?]+(?:\s|$)|\n+|$)", re.DOTALL)


def split_sentences(text: str) -> list[str]:
    return [m.group().strip() for m in _SENT.finditer(text) if m.group().strip()]


def echo_brain(text: str) -> Iterator[str]:
    yield f"You said: {text}"


def command_brain(command: str):
    """Run `command` with the transcript appended as its last argument.

    Streams the program's stdout, yielding complete sentences as they arrive so
    TTS can start early. Its stderr passes through to the terminal. If the
    reply is abandoned mid-way (barge-in), the program is terminated.
    """
    argv = shlex.split(command)
    if not argv:
        raise ValueError("the command brain needs a command (--brain-cmd)")

    def run(text: str) -> Iterator[str]:
        proc = subprocess.Popen([*argv, text], stdout=subprocess.PIPE, text=True,
                                bufsize=1)
        buf = ""
        assert proc.stdout
        try:
            for line in proc.stdout:
                buf += line
                sents = split_sentences(buf)
                # keep the last (possibly incomplete) sentence in the buffer;
                # the space stands in for the line break split_sentences ate
                if len(sents) > 1:
                    yield from sents[:-1]
                    buf = sents[-1] + " "
            if buf.strip():
                yield buf.strip()
        finally:
            if proc.poll() is None:
                proc.terminate()
            code = proc.wait()
            # a negative code is our own terminate() after a barge-in
            if code > 0:
                print(f"brain command exited with status {code}: {command}",
                      file=sys.stderr)
    return run


BRAINS = {
    "echo": lambda **_: echo_brain,
    "command": lambda command="", **_: command_brain(command),
}

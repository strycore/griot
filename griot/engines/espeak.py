"""espeak-ng: a formant synthesizer. Robotic, instant, no GPU, ~100 languages.

The engine for small machines, and a fallback that always works. Voices are
espeak's language codes (`en-us`, `fr`, ...).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from griot.audio import Audio, AudioFormatError, from_wav
from griot.engines import Engine, EngineError, EngineUnavailableError, Voice

log = logging.getLogger(__name__)

DEFAULT_COMMAND = "espeak-ng"
TIMEOUT_S = 30.0
# `espeak-ng --voices` prints: Pty Language Age/Gender VoiceName File Other...
_VOICE_LANGUAGE_COLUMN = 1


class Knob(StrEnum):
    """Style keys this engine understands, and the flag each one sets."""

    SPEED = "speed"          # words per minute
    PITCH = "pitch"          # 0-99
    AMPLITUDE = "amplitude"  # 0-200

    @property
    def flag(self) -> str:
        return {Knob.SPEED: "-s", Knob.PITCH: "-p", Knob.AMPLITUDE: "-a"}[self]


class EspeakEngine(Engine):
    name = "espeak"

    def __init__(self, settings: Mapping[str, Any]) -> None:
        super().__init__(settings)
        self.command = str(settings.get("command", DEFAULT_COMMAND))

    def available(self) -> bool:
        return shutil.which(self.command) is not None

    def voices(self) -> list[Voice]:
        if not self.available():
            return []
        try:
            listing = self._run(["--voices"], None).decode(errors="replace")
        except EngineError as error:
            log.warning("could not list espeak voices: %s", error)
            return []
        codes = [line.split()[_VOICE_LANGUAGE_COLUMN]
                 for line in listing.splitlines()[1:] if line.split()]
        return [Voice(id=code.lower(), engine=self.name, params={"voice": code})
                for code in codes]

    def synthesize(self, text: str, voice: Voice, style: Mapping[str, Any]) -> Audio:
        args = ["--stdin", "--stdout", "-v", str(voice.params["voice"])]
        for knob in Knob:
            if knob in style:
                args += [knob.flag, str(int(style[knob]))]
        try:
            return from_wav(self._run(args, text.encode()))
        except AudioFormatError as error:
            raise EngineError(f"espeak returned unusable audio: {error}") from error

    def _run(self, args: list[str], stdin: bytes | None) -> bytes:
        try:
            done = subprocess.run([self.command, *args], input=stdin, capture_output=True,
                                  timeout=TIMEOUT_S, check=False)
        except FileNotFoundError as error:
            raise EngineUnavailableError(f"{self.command} is not installed") from error
        except subprocess.TimeoutExpired as error:
            raise EngineError(f"{self.command} timed out after {TIMEOUT_S:.0f}s") from error
        if done.returncode != 0:
            detail = done.stderr.decode(errors="replace").strip()[:300]
            raise EngineError(f"{self.command} exited with {done.returncode}: {detail}")
        return done.stdout

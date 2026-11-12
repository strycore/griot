"""Chatterbox, reached through a Chatterbox-TTS-Server instance over HTTP.

Neural, GPU-hungry, clones a voice from a short wav. The server keeps two
folders of wavs: its bundled "predefined" voices and the user's own
"reference" clips. Both show up here as voices, named after the file.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Mapping
from enum import StrEnum
from pathlib import PurePath
from typing import Any

from griot.audio import Audio, AudioFormatError, from_wav
from griot.engines import Engine, EngineError, EngineUnavailableError, Voice

log = logging.getLogger(__name__)

DEFAULT_URL = "http://localhost:8005"
PROBE_TIMEOUT_S = 2.0
SYNTHESIS_TIMEOUT_S = 120.0


class Mode(StrEnum):
    """How the server finds the wav behind a voice."""

    PREDEFINED = "predefined"
    CLONE = "clone"


class ChatterboxEngine(Engine):
    name = "chatterbox"

    def __init__(self, settings: Mapping[str, Any]) -> None:
        super().__init__(settings)
        self.url = str(settings.get("url", DEFAULT_URL)).rstrip("/")

    def available(self) -> bool:
        try:
            info = self._get_json("/api/model-info")
        except EngineError:
            return False
        return bool(isinstance(info, dict) and info.get("loaded"))

    def voices(self) -> list[Voice]:
        try:
            predefined = self._get_json("/get_predefined_voices")
            reference = self._get_json("/get_reference_files")
        except EngineError as error:
            log.debug("chatterbox voices unavailable: %s", error)
            return []
        found = [self._voice(entry["filename"], Mode.PREDEFINED) for entry in predefined]
        found += [self._voice(filename, Mode.CLONE) for filename in reference]
        return found

    def _voice(self, filename: str, mode: Mode) -> Voice:
        return Voice(id=PurePath(filename).stem.lower(), engine=self.name,
                     params={"file": filename, "mode": mode.value})

    def synthesize(self, text: str, voice: Voice, style: Mapping[str, Any]) -> Audio:
        mode = Mode(voice.params.get("mode", Mode.PREDEFINED))
        file_field = ("predefined_voice_id" if mode is Mode.PREDEFINED
                      else "reference_audio_filename")
        request = {**style, "text": text, "voice_mode": mode.value,
                   file_field: voice.params["file"], "output_format": "wav",
                   "stream": False}
        wav = self._request("/tts", json.dumps(request).encode(), SYNTHESIS_TIMEOUT_S)
        try:
            return from_wav(wav)
        except AudioFormatError as error:
            raise EngineError(f"chatterbox returned unusable audio: {error}") from error

    def _get_json(self, path: str) -> Any:
        return json.loads(self._request(path, None, PROBE_TIMEOUT_S))

    def _request(self, path: str, body: bytes | None, timeout: float) -> bytes:
        request = urllib.request.Request(
            self.url + path, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:300]
            raise EngineError(f"chatterbox server said {error.code}: {detail}") from error
        except OSError as error:  # refused, timed out, DNS...
            raise EngineUnavailableError(
                f"chatterbox server not reachable at {self.url}: {error}") from error

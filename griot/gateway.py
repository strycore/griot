"""The gateway: picks a voice and its engine, then streams speech as WAV.

`Gateway` is the engine-neutral core (no HTTP in it, so it is easy to test and
to embed). `make_server` wraps it in the HTTP API clients use:

    POST /speak   {"text": "...", "voice": "emily", "style": "dramatic"}
                  -> audio/wav, streamed piece by piece as it is synthesized
    GET  /voices  -> every voice that can be asked for, and its engine
    GET  /styles  -> style names, descriptions, and the engines each covers
    GET  /health  -> which engines are usable right now
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator, Mapping
from enum import StrEnum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from griot import text as text_chunks
from griot.audio import Audio, stream_header
from griot.config import STYLE_DESCRIPTION_KEY, Config, ConfigError
from griot.engines import ENGINES, Engine, EngineError, EngineUnavailableError, Voice

log = logging.getLogger(__name__)

# How long a listing of an engine's voices is trusted before asking again.
VOICE_CACHE_SECONDS = 30.0
# `engine:voice` asks one engine directly, skipping aliases and lookup order.
ENGINE_SEPARATOR = ":"
# Clients written against Chatterbox name voices after their wav file.
LEGACY_VOICE_SUFFIX = ".wav"
MAX_REQUEST_BYTES = 1_000_000


class Route(StrEnum):
    SPEAK = "/speak"
    VOICES = "/voices"
    STYLES = "/styles"
    HEALTH = "/health"


class RequestError(Exception):
    """The request itself is wrong; `status` is what the client is told."""

    status = HTTPStatus.BAD_REQUEST


class UnknownVoiceError(RequestError):
    status = HTTPStatus.NOT_FOUND


class Gateway:
    def __init__(self, config: Config, engines: Mapping[str, Engine] | None = None) -> None:
        self.config = config
        self.engines: Mapping[str, Engine] = (
            engines if engines is not None else _build_engines(config))
        self._voice_cache: dict[str, tuple[float, list[Voice]]] = {}

    def voices(self) -> list[Voice]:
        """Every voice on offer: configured aliases first, then each engine's own."""
        found: dict[str, Voice] = {}
        for voice_id, entry in self.config.voices.items():
            params = {key: value for key, value in entry.items() if key != "engine"}
            found[voice_id] = Voice(id=voice_id, engine=entry["engine"], params=params)
        for name in self.engines:
            for voice in self._engine_voices(name):
                found.setdefault(voice.id, voice)
        return list(found.values())

    def _engine_voices(self, name: str) -> list[Voice]:
        cached = self._voice_cache.get(name)
        now = time.monotonic()
        if cached and now - cached[0] < VOICE_CACHE_SECONDS:
            return cached[1]
        listed = self.engines[name].voices()
        if listed:  # never cache "none": the engine may just be starting up
            self._voice_cache[name] = (now, listed)
        return listed

    def resolve_voice(self, requested: str | None) -> Voice:
        wanted = (requested or self.config.default_voice).strip().lower()
        wanted = wanted.removesuffix(LEGACY_VOICE_SUFFIX)
        if not wanted:
            raise RequestError("no voice given and no default_voice configured")
        engine_name, separator, voice_id = wanted.partition(ENGINE_SEPARATOR)
        if separator:
            if engine_name not in self.engines:
                raise UnknownVoiceError(f"no engine named '{engine_name}'")
            candidates = self._engine_voices(engine_name)
        else:
            voice_id, candidates = wanted, self.voices()
        for voice in candidates:
            if voice.id == voice_id:
                return voice
        down = [name for name, engine in self.engines.items() if not engine.available()]
        hint = f" (engines not available right now: {', '.join(down)})" if down else ""
        raise UnknownVoiceError(f"no voice named '{wanted}'{hint}; see GET {Route.VOICES}")

    def style_for(self, name: str | None, engine: str) -> Mapping[str, Any]:
        """An engine's knobs for a style. A style the engine has no entry for
        is not an error: the text is still spoken, just plainly."""
        if not name:
            return {}
        style = self.config.styles.get(name)
        if style is None:
            known = ", ".join(self.config.styles) or "none configured"
            raise RequestError(f"no style named '{name}' (known: {known})")
        knobs = style.get(engine)
        if knobs is None:
            log.info("style '%s' has no settings for engine %s; speaking plainly",
                     name, engine)
            return {}
        return dict(knobs)

    def speak(self, text: str, voice: str | None = None,
              style: str | None = None) -> tuple[Voice, Iterator[Audio]]:
        """Resolve the request, then return the voice and a lazy audio stream.

        Request errors are raised here; engine errors surface while iterating.
        """
        pieces = text_chunks.chunk(text, self.config.chunk_chars)
        if not pieces:
            raise RequestError("there is no text to speak")
        chosen = self.resolve_voice(voice)
        engine = self.engines[chosen.engine]
        knobs = self.style_for(style, chosen.engine)
        return chosen, (engine.synthesize(piece, chosen, knobs) for piece in pieces)

    def styles(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                STYLE_DESCRIPTION_KEY: style.get(STYLE_DESCRIPTION_KEY, ""),
                "engines": [key for key in style if key != STYLE_DESCRIPTION_KEY],
            }
            for name, style in self.config.styles.items()
        }

    def health(self) -> dict[str, Any]:
        return {
            "default_voice": self.config.default_voice,
            "engines": {name: {"available": engine.available()}
                        for name, engine in self.engines.items()},
        }


def _build_engines(config: Config) -> dict[str, Engine]:
    engines: dict[str, Engine] = {}
    for name, settings in config.engines.items():
        if name not in ENGINES:
            raise ConfigError(f"unknown engine '{name}' (known: {', '.join(ENGINES)})")
        engines[name] = ENGINES[name](settings)
    return engines


def make_server(gateway: Gateway) -> ThreadingHTTPServer:
    class Handler(_Handler):
        pass

    Handler.gateway = gateway
    return ThreadingHTTPServer((gateway.config.host, gateway.config.port), Handler)


class _Handler(BaseHTTPRequestHandler):
    gateway: Gateway
    server_version = "griot"

    def log_message(self, format: str, *args: Any) -> None:
        log.debug("%s %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        gateway = self.gateway
        if self.path == Route.VOICES:
            self._send_json(HTTPStatus.OK, [
                {"id": voice.id, "engine": voice.engine} for voice in gateway.voices()])
        elif self.path == Route.STYLES:
            self._send_json(HTTPStatus.OK, gateway.styles())
        elif self.path == Route.HEALTH:
            self._send_json(HTTPStatus.OK, gateway.health())
        else:
            self._send_error(HTTPStatus.NOT_FOUND, f"no such resource: {self.path}")

    def do_POST(self) -> None:
        if self.path != Route.SPEAK:
            self._send_error(HTTPStatus.NOT_FOUND, f"no such resource: {self.path}")
            return
        started = time.monotonic()
        try:
            request = self._read_json()
            text = request.get("text")
            if not isinstance(text, str):
                raise RequestError("'text' is required and must be a string")
            voice, stream = self.gateway.speak(text, request.get("voice"),
                                               request.get("style"))
            # Synthesize the first piece before committing to a 200, so a
            # failing engine is reported as an error rather than as silence.
            first = next(stream)
        except RequestError as error:
            self._send_error(error.status, str(error))
            return
        except EngineUnavailableError as error:
            self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, str(error))
            return
        except EngineError as error:
            log.error("engine failed: %s", error)
            self._send_error(HTTPStatus.BAD_GATEWAY, str(error))
            return

        first_audio = time.monotonic() - started
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "audio/wav")
        self.end_headers()  # no length: the body ends when the connection closes
        seconds, outcome = 0.0, "complete"
        try:
            self.wfile.write(stream_header(first.sample_rate))
            for audio in self._rest(first, stream):
                if audio.sample_rate != first.sample_rate:
                    raise EngineError(
                        f"sample rate changed mid-stream ({first.sample_rate} -> "
                        f"{audio.sample_rate})")
                self.wfile.write(audio.pcm)
                self.wfile.flush()
                seconds += audio.seconds
        except (BrokenPipeError, ConnectionResetError):
            outcome = "client went away"  # barge-in, or a newer utterance
        except EngineError as error:
            outcome = "cut short"
            log.error("engine failed mid-stream: %s", error)
        log.info("spoke %d chars as %s (%s): first audio %.2fs, %.1fs of audio in %.2fs, %s",
                 len(text), voice.id, voice.engine, first_audio, seconds,
                 time.monotonic() - started, outcome)

    @staticmethod
    def _rest(first: Audio, stream: Iterator[Audio]) -> Iterator[Audio]:
        yield first
        yield from stream

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise RequestError(f"expected a JSON body of at most {MAX_REQUEST_BYTES} bytes")
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError as error:
            raise RequestError(f"body is not valid JSON: {error}") from error
        if not isinstance(body, dict):
            raise RequestError("body must be a JSON object")
        return body

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, detail: str) -> None:
        log.warning("%s %s -> %d %s", self.command, self.path, status, detail)
        self._send_json(status, {"detail": detail})

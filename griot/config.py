"""Loading `griot.toml`: the server, its engines, voice aliases and styles."""
from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_ENV = "GRIOT_CONFIG"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "griot.toml"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8004
DEFAULT_CHUNK_CHARS = 200
# Keys of a `[styles.<name>]` table that are not an engine's settings.
STYLE_DESCRIPTION_KEY = "description"


class ConfigError(ValueError):
    """`griot.toml` is missing something or names something unknown."""


@dataclass(frozen=True)
class Config:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    default_voice: str = ""
    chunk_chars: int = DEFAULT_CHUNK_CHARS
    # engine name -> its settings, in the order voices are looked up
    engines: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    # voice id -> {"engine": ..., engine params...}
    voices: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    # style name -> {"description": ..., "<engine>": {knobs}}
    styles: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG_PATH))


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
    except FileNotFoundError as error:
        raise ConfigError(f"no config file at {path} (set {CONFIG_ENV} to point at one)") \
            from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: {error}") from error
    return parse(raw)


def parse(raw: Mapping[str, Any]) -> Config:
    server = raw.get("server", {})
    engines = raw.get("engines", {})
    if not engines:
        raise ConfigError("no engines configured: add an [engines.<name>] table")
    voices = raw.get("voices", {})
    for voice_id, voice in voices.items():
        if voice.get("engine") not in engines:
            raise ConfigError(
                f"voice '{voice_id}' names engine {voice.get('engine')!r}, "
                f"which is not configured (have: {', '.join(engines)})")
    return Config(
        host=server.get("host", DEFAULT_HOST),
        port=server.get("port", DEFAULT_PORT),
        default_voice=server.get("default_voice", ""),
        chunk_chars=server.get("chunk_chars", DEFAULT_CHUNK_CHARS),
        engines=engines,
        voices={voice_id.lower(): voice for voice_id, voice in voices.items()},
        styles=raw.get("styles", {}),
    )

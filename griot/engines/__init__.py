"""TTS engines: one adapter per backend, all behind the same small interface.

To add an engine, subclass `Engine` in a new module here and list it in
`ENGINES`. An adapter's whole job is: say whether its backend is usable, list
the voices it offers, and turn one piece of text into `Audio`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from griot.audio import Audio


class EngineError(Exception):
    """An engine failed to synthesize."""


class EngineUnavailableError(EngineError):
    """An engine's backend is not installed or not reachable."""


@dataclass(frozen=True)
class Voice:
    """A voice a client can ask for by `id`; `params` are the engine's own."""

    id: str
    engine: str
    params: Mapping[str, Any] = field(default_factory=dict)


class Engine(ABC):
    """A text-to-speech backend."""

    name: ClassVar[str]

    def __init__(self, settings: Mapping[str, Any]) -> None:
        self.settings = settings

    @abstractmethod
    def available(self) -> bool:
        """Whether the backend can synthesize right now."""

    @abstractmethod
    def voices(self) -> list[Voice]:
        """The voices this engine offers. Empty when unavailable."""

    @abstractmethod
    def synthesize(self, text: str, voice: Voice, style: Mapping[str, Any]) -> Audio:
        """Speak one piece of text. `style` holds this engine's own knobs."""


def _registry() -> dict[str, type[Engine]]:
    from griot.engines.chatterbox import ChatterboxEngine
    from griot.engines.espeak import EspeakEngine

    return {engine.name: engine for engine in (ChatterboxEngine, EspeakEngine)}


ENGINES: dict[str, type[Engine]] = _registry()

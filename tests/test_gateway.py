import io
import json
import threading
import urllib.error
import urllib.request
import wave
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from griot.audio import Audio
from griot.config import ConfigError, parse
from griot.engines import Engine, EngineError, EngineUnavailableError, Voice
from griot.gateway import Gateway, RequestError, UnknownVoiceError, make_server

RATE = 8000


class FakeEngine(Engine):
    """Speaks each piece as one sample per character; records what it was asked."""

    def __init__(self, name: str, voice_ids: list[str], up: bool = True) -> None:
        super().__init__({})
        self.name = name  # type: ignore[misc]
        self.voice_ids, self.up = voice_ids, up
        self.calls: list[tuple[str, str, Mapping[str, Any]]] = []
        self.fail_on: str | None = None

    def available(self) -> bool:
        return self.up

    def voices(self) -> list[Voice]:
        if not self.up:
            return []
        return [Voice(id=v, engine=self.name, params={"native": v}) for v in self.voice_ids]

    def synthesize(self, text: str, voice: Voice, style: Mapping[str, Any]) -> Audio:
        if not self.up:
            raise EngineUnavailableError(f"{self.name} is down")
        if self.fail_on and self.fail_on in text:
            raise EngineError(f"{self.name} choked")
        self.calls.append((text, voice.id, style))
        return Audio(RATE, b"\x01\x00" * len(text))


CONFIG = {
    "server": {"host": "127.0.0.1", "port": 0, "default_voice": "emily", "chunk_chars": 40},
    "engines": {"neural": {}, "basic": {}},
    "voices": {"Robot": {"engine": "basic", "native": "en"}},
    "styles": {"dramatic": {"description": "Big", "neural": {"exaggeration": 1.3}}},
}


@pytest.fixture
def engines() -> dict[str, FakeEngine]:
    return {"neural": FakeEngine("neural", ["emily", "shared"]),
            "basic": FakeEngine("basic", ["en", "shared"])}


@pytest.fixture
def gateway(engines: dict[str, FakeEngine]) -> Gateway:
    return Gateway(parse(CONFIG), engines)


def test_voices_lists_aliases_then_each_engine_first_engine_winning(gateway: Gateway):
    listed = {voice.id: voice.engine for voice in gateway.voices()}
    assert listed == {"robot": "basic", "emily": "neural", "shared": "neural", "en": "basic"}


@pytest.mark.parametrize(("requested", "voice_id", "engine"), [
    (None, "emily", "neural"),          # the default
    ("Emily.wav", "emily", "neural"),   # legacy file-style name
    ("robot", "robot", "basic"),        # alias
    ("shared", "shared", "neural"),     # first configured engine wins
    ("basic:shared", "shared", "basic"),  # ...unless one is asked for directly
])
def test_voice_resolution(gateway: Gateway, requested, voice_id, engine):
    voice = gateway.resolve_voice(requested)
    assert (voice.id, voice.engine) == (voice_id, engine)


def test_unknown_voice_names_engines_that_are_down(gateway: Gateway, engines):
    engines["neural"].up = False
    with pytest.raises(UnknownVoiceError, match="not available right now: neural"):
        gateway.resolve_voice("emily")


def test_alias_keeps_its_engine_params(gateway: Gateway):
    assert gateway.resolve_voice("robot").params == {"native": "en"}


def test_style_is_per_engine_and_missing_entries_speak_plainly(gateway: Gateway):
    assert gateway.style_for("dramatic", "neural") == {"exaggeration": 1.3}
    assert gateway.style_for("dramatic", "basic") == {}
    assert gateway.style_for(None, "neural") == {}
    with pytest.raises(RequestError, match="no style named 'nope'"):
        gateway.style_for("nope", "neural")


def test_speak_chunks_text_and_passes_voice_and_style(gateway: Gateway, engines):
    voice, stream = gateway.speak("Hi. " + "Short one. " * 5, style="dramatic")
    audio = list(stream)
    assert voice.id == "emily"
    assert [text for text, _, _ in engines["neural"].calls] == [
        "Hi.", "Short one. Short one. Short one.", "Short one. Short one."]
    assert all(style == {"exaggeration": 1.3} for _, _, style in engines["neural"].calls)
    assert len(audio) == 3


def test_speak_is_lazy_so_an_abandoned_stream_stops_synthesis(gateway: Gateway, engines):
    _, stream = gateway.speak("One. Two. " + "Three is long enough to be its own piece. " * 3)
    next(stream)
    assert len(engines["neural"].calls) == 1


def test_config_rejects_a_voice_on_an_unconfigured_engine():
    with pytest.raises(ConfigError, match="voice 'x' names engine 'ghost'"):
        parse({"engines": {"basic": {}}, "voices": {"x": {"engine": "ghost"}}})


def test_config_requires_an_engine():
    with pytest.raises(ConfigError, match="no engines configured"):
        parse({})


# --- over HTTP ----------------------------------------------------------------

@pytest.fixture
def url(gateway: Gateway) -> Iterator[str]:
    server = make_server(gateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def post(url: str, body: Any) -> tuple[int, bytes]:
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url + "/speak", data=data)) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def test_http_speak_streams_a_wav(url: str):
    status, body = post(url, {"text": "Hello there. General Kenobi."})
    assert status == 200
    with wave.open(io.BytesIO(body)) as wav:
        assert wav.getframerate() == RATE
    assert len(body) == 44 + 2 * (len("Hello there.") + len("General Kenobi."))


@pytest.mark.parametrize(("body", "status", "detail"), [
    ({"text": "x", "voice": "nobody"}, 404, "no voice named 'nobody'"),
    ({"text": "x", "style": "nope"}, 400, "no style named 'nope'"),
    ({"voice": "emily"}, 400, "'text' is required"),
    ({"text": "  "}, 400, "no text to speak"),
    (b"garbage", 400, "not valid JSON"),
])
def test_http_request_errors(url: str, body, status: int, detail: str):
    got_status, got_body = post(url, body)
    assert got_status == status
    assert detail in json.loads(got_body)["detail"]


def test_http_engine_down_is_503_and_failing_is_502(url: str, engines):
    engines["basic"].up = False
    assert post(url, {"text": "x", "voice": "robot"})[0] == 503
    engines["neural"].fail_on = "x"
    assert post(url, {"text": "x"})[0] == 502


def test_http_mid_stream_failure_ends_the_audio_early(url: str, engines):
    engines["neural"].fail_on = "Boom"
    status, body = post(url, {"text": "Fine so far. Boom goes the second piece."})
    assert status == 200
    assert len(body) == 44 + 2 * len("Fine so far.")


def test_http_listings(url: str):
    def get(path: str) -> Any:
        with urllib.request.urlopen(url + path) as response:
            return json.load(response)

    assert {"id": "robot", "engine": "basic"} in get("/voices")
    assert get("/styles") == {"dramatic": {"description": "Big", "engines": ["neural"]}}
    assert get("/health")["engines"] == {"neural": {"available": True},
                                        "basic": {"available": True}}

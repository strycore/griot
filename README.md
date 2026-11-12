# griot

A local text-to-speech **gateway**: one small HTTP service that speaks through whichever
TTS engine you have, plus a hands-free [voice loop](voice/) on top of it.

griot owns the API that clients talk to; each engine sits behind a small adapter. The
gateway is standard-library Python with no dependencies, so the same setup runs on a
GPU workstation with a neural voice-cloning engine and on a small machine with nothing
but espeak.

```
say.sh / voice loop / any client
            │  POST /speak {text, voice, style}
            ▼
     griot gateway :8004 ──┬──▶ chatterbox  (neural, GPU, clones a voice from a wav)
     (splits text, streams │
      WAV as it is made)   └──▶ espeak      (formant synth, instant, no GPU)
```

## Run

```sh
./run.sh                      # the gateway, on http://localhost:8004
engines/chatterbox/run.sh     # the Chatterbox engine, if you want it (see its README)
```

The gateway needs Python ≥ 3.11 and nothing else. It starts fine with an engine missing
or down — voices from that engine are simply unavailable until it is up.

## Speak from the command line

```sh
./say.sh "Hello there, this is my local voice."
./say.sh -p dramatic "[gasp] The soufflé has fallen!"   # style
./say.sh -e glados "Oh, it's you."                      # audio effect
./say.sh -v gianna "Cloned voice text."                 # another voice
./say.sh -v robot "No GPU required."                    # espeak
./say.sh -l                                             # list styles, effects, voices
```

Audio is streamed: the gateway synthesizes the text sentence by sentence and playback
starts as soon as the first sentence is ready (about half a second with Chatterbox on an
RX 7800 XT, instantly with espeak).

Effects (`-e`) filter the audio through sox/ffmpeg on the client: `glados`, `claptrap`,
`robot`, `ethereal`. Recipes live in the `fx_pipe` function in `say.sh`. Styles, effects
and voices compose: `./say.sh -p dramatic -e glados -v gianna "..."`.

## API

```sh
curl -N localhost:8004/speak -d '{"text": "Hello world"}' | aplay -q -
curl -N localhost:8004/speak -d '{"text": "Hello", "voice": "gianna", "style": "calm"}' -o hello.wav
```

| | |
|---|---|
| `POST /speak` | `{"text", "voice"?, "style"?}` → streamed `audio/wav` (mono, 16-bit). Errors are JSON `{"detail"}`: 400 bad request or unknown style, 404 unknown voice, 503 engine down, 502 engine failed. |
| `GET /voices` | every voice that can be asked for, and the engine behind it |
| `GET /styles` | style names, descriptions, and which engines have settings for each |
| `GET /health` | which engines are usable right now |

## Voices, styles and engines — `griot.toml`

- **Engines** are enabled by an `[engines.<name>]` table. Each lists its own voices:
  Chatterbox offers one per wav file it knows, espeak one per language (`en-us`, `fr-fr`…).
- **Voices** are asked for by name, case-insensitively (`emily`). When two engines share
  a name, the first engine in the file wins; `engine:voice` (`espeak:en-us`) asks one
  directly. A `[voices.<name>]` table gives a voice another name (`robot` → espeak `en-us`).
- **Styles** are named deliveries (`calm`, `narrator`, `newsreader`, `dramatic`, `hyped`).
  Each engine has its own knobs for a style; an engine with no entry for one just speaks
  plainly. Add a style by copying a `[styles.<name>]` table.

Chatterbox voices also honor paralinguistic tags inline in the text: `[laugh]`, `[sigh]`,
`[gasp]`, `[cough]`, `[chuckle]`…

## Adding an engine

An engine is one class in `griot/engines/` with three methods — is it usable, which
voices does it have, turn this text into audio — registered in `griot/engines/__init__.py`.
`espeak.py` is the short example (a command-line program); `chatterbox.py` shows an
engine reached over HTTP. The gateway handles text splitting, streaming and the WAV
framing, so an adapter never deals with any of that.

## Development

```sh
uv sync                 # dev tools only: pytest, ruff, mypy
uv run pytest
uv run ruff check . && uv run mypy
```

## Layout

- `griot/` — the gateway (`gateway.py`: API and voice/style resolution; `engines/`: adapters)
- `griot.toml` — engines, voice aliases, styles
- `say.sh` — command-line client with audio effects
- `voice/` — the interruptible voice loop (mic → speech-to-text → brain → griot)
- `face/` — small status window for the voice loop
- `engines/chatterbox/` — environment and config for the Chatterbox engine; the server
  itself is the upstream project, pinned as a git submodule

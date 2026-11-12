# Chatterbox engine

Resemble AI's [Chatterbox](https://github.com/resemble-ai/chatterbox) models (zero-shot
voice cloning from a short wav), served by
[devnen/Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server). griot
reaches it over HTTP through the adapter in `griot/engines/chatterbox.py`.

Both upstream projects are frozen or slow-moving (Chatterbox was retired in August 2026),
so nothing of theirs is copied into griot:

- `server/` — the server, **unmodified**, as a git submodule pinned to a commit.
- `pyproject.toml`, `uv.lock` — our environment for it: ROCm 6.1 torch wheels for an AMD
  RX 7800 XT and the dep-stripped Chatterbox package (see the comments in `pyproject.toml`).
- `config.yaml` — our server configuration (port 8005, model, defaults).
- `reference_audio/` — your own wav clips to clone; each becomes a griot voice named
  after the file. The bundled voices live in `server/voices/`.

## Setup

Requires Python 3.10 and a working ROCm install.

```sh
git submodule update --init
cd engines/chatterbox && uv sync
```

## Run

```sh
./run.sh
```

Sets `HSA_OVERRIDE_GFX_VERSION=11.0.0` (gfx1101 → gfx1100 kernels, required for the
ROCm 6.1 wheels) and starts the server on <http://localhost:8005>, where its own web UI
and API docs (`/docs`) also live. The model downloads on first run.

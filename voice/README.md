# voice — interruptible voice loop for griot

A hands-free conversation layer on top of griot's TTS: **mic → STT → brain → griot TTS**,
with **barge-in** (talk over the bot and it stops). A lightweight client of the griot
server — no torch, ~390 MB venv (faster-whisper CPU + onnxruntime VAD).

```
mic (16 kHz)  ──▶  Silero VAD  ──▶  faster-whisper  ──▶  brain  ──▶  griot /tts ──▶ aplay
   │  (always on)      segments turns     small.en (CPU)    reply       streamed     playback
   └──────────────── onset while bot speaks ⇒ Speaker.stop() (barge-in) ◀───────────────┘
```

## Setup
```sh
uv venv --python 3.12 .venv && uv pip install -r requirements.txt
```
The Silero VAD v6 model is vendored in `models/`. faster-whisper downloads `small.en`
to its cache on first run.

## Run
griot must be up (`cd .. && ./run.sh`), then:
```sh
./talk.sh                                   # echo brain: repeats what it hears
./talk.sh --brain claude --voice Emily.wav  # talk to the maestro persona
./talk.sh --brain claude --system ~/Nextcloud/robots/maestro/CLAUDE.md
```
Ctrl-C to stop.

## Pieces
- `mic.py` — always-on mic + Silero VAD v6 (onnxruntime). Segments utterances and fires
  `on_speech_start` for barge-in. Run directly to smoke-test VAD onsets.
- `stt.py` — faster-whisper wrapper (CPU int8 `small.en`). Run directly to print live
  transcripts.
- `tts.py` — griot streaming client; `Speaker.speak()` blocks, `Speaker.stop()` cuts in.
- `brain.py` — pluggable replies: `echo`, `claude` (headless `claude -p --continue`).
- `converse.py` — the loop. `--no-barge-in` mutes the mic while the bot talks (use on
  open speakers without echo cancellation; closed headset is fine with barge-in on).

## Barge-in & echo
Closed headset (default here): barge-in on — VAD onset during playback kills the bot.
Open speakers: either `--no-barge-in`, or load PipeWire `module-echo-cancel` so the mic
doesn't hear the bot.

## Tuning
VAD knobs live in `mic.VadConfig` (threshold, trailing-silence ms, min-speech ms,
preroll, onset frames). STT model in `stt.MODEL` — swap to `large-v3-turbo` (or point at
whisper.cpp-Vulkan) if you want the GPU and lower latency.
```

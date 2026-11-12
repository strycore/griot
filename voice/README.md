# voice — interruptible voice loop for griot

A hands-free conversation layer on top of griot's TTS: **mic → STT → brain → griot TTS**,
with **barge-in** (talk over the bot and it stops). A lightweight client of the griot
gateway — no torch, ~390 MB venv (faster-whisper CPU + onnxruntime VAD).

```
mic (16 kHz)  ──▶  Silero VAD  ──▶  faster-whisper  ──▶  brain  ──▶  griot /speak ──▶ aplay
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
The griot gateway must be up (`cd .. && ./run.sh`, plus whichever engine your voice
needs), then:
```sh
./talk.sh                                        # echo brain: repeats what it hears
VOICE_BRAIN_CMD="my-assistant reply" ./talk.sh   # an external program answers
```
Ctrl-C to stop.

## Brain
griot does no inference. The **brain** is whatever turns a transcript into a reply:
`echo` (built in, for testing) or `command`, which runs any program you name with the
transcript appended as its last argument and speaks what it prints, sentence by sentence
as the output arrives. A leading emoji in the reply sets the face window's expression
instead of being spoken. That one seam is how an assistant or orchestrator plugs in —
e.g. [baton](https://github.com/strycore/baton): `VOICE_BRAIN_CMD="baton voice reply"`.

## Pieces
- `mic.py` — always-on mic + Silero VAD v6 (onnxruntime). Segments utterances and fires
  `on_speech_start` for barge-in. Run directly to smoke-test VAD onsets.
- `stt.py` — faster-whisper wrapper (CPU int8 `small.en`). Run directly to print live
  transcripts.
- `tts.py` — griot streaming client; `Speaker.speak()` blocks, `Speaker.stop()` cuts in.
- `brain.py` — pluggable replies: `echo`, `command` (any external program).
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

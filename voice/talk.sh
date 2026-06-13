#!/usr/bin/env bash
# Start an interruptible voice conversation against the local griot TTS server.
#
#   ./talk.sh                      # SM57 on Scarlett -> maestro (known-good defaults)
#   ./talk.sh --brain echo         # override any flag; args pass through to converse.py
#   ./talk.sh --device 8 --channel 0   # e.g. webcam mic instead
#
# Requires griot running at :8004 (cd .. && ./run.sh).
#
# Defaults below capture the dialed-in setup: SM57 on the Scarlett XLR (device 17,
# channel 0 -- the mic only appears as stereo ch0), open-mic so barge-in is off
# (mic mutes while the bot talks), claude brain with the maestro persona.
# Device indices can shift across reboots/replugs -- check `python meter.py -l`.
set -euo pipefail
cd "$(dirname "$0")"

DEVICE="${VOICE_DEVICE:-17}"
CHANNEL="${VOICE_CHANNEL:-0}"
BRAIN="${VOICE_BRAIN:-claude}"
VOICE="${VOICE_VOICE:-Emily.wav}"
SYSTEM="${VOICE_SYSTEM:-$HOME/Nextcloud/robots/maestro/CLAUDE.md}"
BRAIN_MODEL="${VOICE_BRAIN_MODEL:-}"   # e.g. haiku, sonnet — faster than default
FACE_SOCK="${VOICE_FACE_SOCK:-${XDG_RUNTIME_DIR:-/tmp}/griot-face.sock}"
SRT_DIR="${VOICE_SRT_DIR:-$(dirname "$0")/transcripts}"
# Barge-in on by default (headphones). Set VOICE_NO_BARGE_IN=1 for open speakers.
NOBARGE=""
if [ -n "${VOICE_NO_BARGE_IN:-}" ]; then NOBARGE="--no-barge-in"; fi

exec .venv/bin/python -u converse.py \
  --device "$DEVICE" --channel "$CHANNEL" \
  --brain "$BRAIN" --voice "$VOICE" $NOBARGE \
  --face-sock "$FACE_SOCK" --srt-dir "$SRT_DIR" \
  ${SYSTEM:+--system "$SYSTEM"} \
  ${BRAIN_MODEL:+--brain-model "$BRAIN_MODEL"} \
  "$@"

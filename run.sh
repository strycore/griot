#!/usr/bin/env bash
# Launch the Chatterbox TTS server (ROCm / RX 7800 XT).
# Web UI + OpenAI-compatible API at http://localhost:8004
cd "$(dirname "$0")"
# RX 7800 XT is gfx1101; the ROCm 6.1 torch wheels only ship gfx1100 compute
# kernels. Without this, detection passes but inference fails with
# "HIP error: invalid device function". 11.0.0 maps gfx1101 -> gfx1100 kernels.
export HSA_OVERRIDE_GFX_VERSION=11.0.0
exec .venv/bin/python server.py "$@"

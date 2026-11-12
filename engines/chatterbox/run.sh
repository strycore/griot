#!/usr/bin/env bash
# Launch the Chatterbox TTS server (ROCm / RX 7800 XT) — the engine behind
# griot's `chatterbox` adapter. Its own web UI is at http://localhost:8005.
#
# The server itself is the unmodified upstream project in ./server (a git
# submodule); this directory only holds what is ours: the environment
# (pyproject.toml), the configuration (config.yaml) and the data folders. The
# server finds those relative to the working directory, hence the cd.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f server/server.py ]; then
  echo "engines/chatterbox/server is empty: run 'git submodule update --init'" >&2
  exit 1
fi
# RX 7800 XT is gfx1101; the ROCm 6.1 torch wheels only ship gfx1100 compute
# kernels. Without this, detection passes but inference fails with
# "HIP error: invalid device function". 11.0.0 maps gfx1101 -> gfx1100 kernels.
export HSA_OVERRIDE_GFX_VERSION=11.0.0
exec .venv/bin/python server/server.py "$@"

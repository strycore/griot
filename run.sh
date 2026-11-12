#!/usr/bin/env bash
# Start the griot gateway (http://localhost:8004). It needs nothing but
# Python >= 3.11. Engines run separately: see engines/ and griot.toml.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m griot "$@"

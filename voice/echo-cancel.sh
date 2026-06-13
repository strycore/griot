#!/usr/bin/env bash
# Load/unload PipeWire echo cancellation so barge-in works on OPEN SPEAKERS
# (the mic no longer hears the bot, so you can run with barge-in enabled).
#
#   ./echo-cancel.sh on        # load AEC, route defaults through it
#   ./echo-cancel.sh off       # unload
#   ./echo-cancel.sh status
#
# Creates two virtual nodes via module-echo-cancel (webrtc AEC):
#   echocancel_source  -- the mic with the speaker signal removed  (capture this)
#   echocancel_sink    -- play here so AEC has the playback reference (TTS out)
# We set both as the system defaults, so aplay (TTS) and the loop's mic both go
# through AEC automatically. On headphones you don't need this at all.
set -euo pipefail

MIC="${VOICE_AEC_MIC:-alsa_input.usb-Focusrite_Scarlett_Solo_USB-00.HiFi__Mic1__source}"
OUT="${VOICE_AEC_SINK:-alsa_output.usb-Focusrite_Scarlett_Solo_USB-00.HiFi__Line__sink}"

case "${1:-status}" in
  on)
    if pactl list modules short | grep -q module-echo-cancel; then
      echo "echo-cancel already loaded."; exit 0
    fi
    pactl load-module module-echo-cancel \
      source_master="$MIC" sink_master="$OUT" \
      source_name=echocancel_source sink_name=echocancel_sink \
      aec_method=webrtc use_master_format=1 \
      source_properties="node.description=EchoCancelMic" \
      sink_properties="node.description=EchoCancelOut" >/dev/null
    pactl set-default-source echocancel_source
    pactl set-default-sink echocancel_sink
    echo "echo-cancel ON — defaults routed through echocancel_{source,sink}."
    echo "Find the AEC mic's index, then run the loop on it with barge-in ON:"
    echo "  .venv/bin/python meter.py -l | grep -i echocancel"
    echo "  VOICE_DEVICE=<index> ./talk.sh        # (no VOICE_NO_BARGE_IN)"
    ;;
  off)
    pactl unload-module module-echo-cancel 2>/dev/null || true
    echo "echo-cancel OFF. Re-select your normal default source/sink if needed."
    ;;
  status)
    pactl list modules short | grep echo-cancel || echo "not loaded"
    ;;
  *)
    echo "usage: $0 on|off|status" >&2; exit 1 ;;
esac

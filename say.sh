#!/usr/bin/env bash
# Quick "read this aloud" via the griot gateway. Audio is streamed: playback
# starts as soon as the first sentence is synthesized, while the rest generates.
#   ./say.sh "Hello there, this is my local voice."
#   ./say.sh -p dramatic "The soufflé has fallen!"   (style, see griot.toml)
#   ./say.sh -e glados "You will be baked."          (effect: glados|claptrap|robot|ethereal)
#   ./say.sh -v gianna "Cloned voice text."          (any voice from any engine)
#   ./say.sh -v robot "No GPU required."             (espeak)
#   ./say.sh -l                                      (list styles, effects and voices)
# Chatterbox voices also honor tags in the text: [laugh] [sigh] [gasp] [cough] ...
set -euo pipefail
HOST="${GRIOT_HOST:-http://localhost:8004}"
VOICE="${GRIOT_VOICE:-}"   # empty: the gateway's default voice
PRESET=""
EFFECT=""

# Effect filters: wav on stdin -> wav on stdout, streaming.
fx_pipe() {
  case "$1" in
    glados)   # passive-aggressive AI: pitch up, subtle warble, sterile slapback
      sox -V1 -t wav - -t wav - pitch 300 tremolo 7 20 echo 0.9 0.6 12 0.2 treble 4 ;;
    claptrap) # hyperactive robot: pitched way up, faster, tinny megaphone edge
      sox -V1 -t wav - -t wav - pitch 550 tempo 1.08 overdrive 6 \
        equalizer 2000 1q 4 highpass 250 lowpass 7000 gain -3 ;;
    robot)    # classic vocoder buzz: flatten all phase information per FFT frame
      ffmpeg -loglevel error -probesize 32 -analyzeduration 0 -fflags nobuffer -i - -af \
        "afftfilt=real='hypot(re,im)*cos(0)':imag='hypot(re,im)*sin(0)':win_size=512:overlap=0.75" \
        -f wav - ;;
    ethereal) # floaty: shimmer chorus, soft echoes, cathedral reverb
      sox -V1 -t wav - -t wav - chorus 0.6 0.9 50 0.4 0.25 2 -t 60 0.32 0.4 1.3 -s \
        echos 0.8 0.5 500 0.12 700 0.15 reverb 85 50 100 100 20 0 gain -2 ;;
  esac
}
KNOWN_FX="glados claptrap robot ethereal"

while [ $# -gt 0 ]; do
  case "$1" in
    -v) VOICE="$2"; shift 2 ;;
    -p) PRESET="$2"; shift 2 ;;
    -e) EFFECT="$2"; shift 2 ;;
    -l) echo "styles (-p):"
        curl -fsS "$HOST/styles" \
          | jq -r 'to_entries[] | "  \(.key)\t\(.value.description)\t[\(.value.engines | join(", "))]"' \
          | column -ts$'\t'
        echo "effects (-e):"
        sed -n 's/^    \([a-z]*\)) *# \(.*\)/  \1\t\2/p' "$0" | column -ts$'\t'
        echo "voices (-v):"
        curl -fsS "$HOST/voices" \
          | jq -r 'group_by(.engine)[] | "  \(.[0].engine)\t\(map(.id) | join(" "))"' \
          | column -ts$'\t' | fold -s -w 100
        exit 0 ;;
    *) break ;;
  esac
done
TEXT="${*:?usage: ./say.sh [-p style] [-e effect] [-v voice] \"text to speak\"}"
if [ -n "$EFFECT" ] && ! grep -qw "$EFFECT" <<<"$KNOWN_FX"; then
  echo "unknown effect: $EFFECT (try ./say.sh -l)" >&2; exit 1
fi
REQ="$(jq -n --arg t "$TEXT" --arg v "$VOICE" --arg s "$PRESET" \
  '{text:$t} + (if $v != "" then {voice:$v} else {} end)
             + (if $s != "" then {style:$s} else {} end)')"
speak() { curl -fsSN "$HOST/speak" -H "Content-Type: application/json" -d "$REQ"; }
if [ -n "$EFFECT" ]; then
  speak | fx_pipe "$EFFECT" | aplay -q - 2>/dev/null
else
  speak | aplay -q - 2>/dev/null
fi || { echo "say.sh: the gateway refused or is down (voices and styles: ./say.sh -l)" >&2; exit 1; }

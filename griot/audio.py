"""The one audio shape engines hand back, and the WAV framing around it."""
from __future__ import annotations

import io
import struct
import wave
from dataclasses import dataclass

SAMPLE_WIDTH_BYTES = 2
CHANNELS = 1
_PCM_FORMAT_TAG = 1
# A streamed WAV cannot know its length up front; this is the conventional
# "unknown / until end of stream" marker players such as aplay understand.
_UNKNOWN_SIZE = 0xFFFFFFFF


class AudioFormatError(ValueError):
    """An engine produced audio the gateway cannot pass on."""


@dataclass(frozen=True)
class Audio:
    """Mono 16-bit little-endian PCM at `sample_rate`."""

    sample_rate: int
    pcm: bytes

    @property
    def seconds(self) -> float:
        return len(self.pcm) / (self.sample_rate * SAMPLE_WIDTH_BYTES * CHANNELS)


def from_wav(data: bytes) -> Audio:
    """Unwrap a WAV file into `Audio`, insisting on mono 16-bit PCM."""
    try:
        with wave.open(io.BytesIO(data)) as wav:
            if wav.getnchannels() != CHANNELS or wav.getsampwidth() != SAMPLE_WIDTH_BYTES:
                raise AudioFormatError(
                    f"expected mono 16-bit audio, got {wav.getnchannels()} channel(s) "
                    f"at {wav.getsampwidth() * 8} bits"
                )
            # Engines writing to a pipe leave a bogus frame count in the header;
            # readframes simply stops at the data that is really there.
            return Audio(wav.getframerate(), wav.readframes(wav.getnframes()))
    except (wave.Error, EOFError) as error:
        raise AudioFormatError(f"not a readable WAV file: {error}") from error


def stream_header(sample_rate: int) -> bytes:
    """A WAV header for a stream of unknown length."""
    byte_rate = sample_rate * CHANNELS * SAMPLE_WIDTH_BYTES
    return b"".join((
        b"RIFF", struct.pack("<I", _UNKNOWN_SIZE), b"WAVE",
        b"fmt ", struct.pack("<IHHIIHH", 16, _PCM_FORMAT_TAG, CHANNELS, sample_rate,
                             byte_rate, CHANNELS * SAMPLE_WIDTH_BYTES,
                             SAMPLE_WIDTH_BYTES * 8),
        b"data", struct.pack("<I", _UNKNOWN_SIZE),
    ))

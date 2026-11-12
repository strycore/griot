import io
import wave

import pytest

from griot.audio import Audio, AudioFormatError, from_wav, stream_header


def make_wav(pcm: bytes, rate: int = 22050, channels: int = 1, width: int = 2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def test_wav_round_trips_to_pcm():
    audio = from_wav(make_wav(b"\x01\x00" * 22050))
    assert audio == Audio(22050, b"\x01\x00" * 22050)
    assert audio.seconds == pytest.approx(1.0)


@pytest.mark.parametrize("kwargs", [{"channels": 2}, {"width": 1}])
def test_anything_but_mono_16_bit_is_refused(kwargs):
    with pytest.raises(AudioFormatError, match="mono 16-bit"):
        from_wav(make_wav(b"\x00" * 8, **kwargs))


def test_garbage_is_refused():
    with pytest.raises(AudioFormatError):
        from_wav(b"not a wav file at all")


def test_stream_header_reads_back_as_a_wav_of_the_right_format():
    pcm = b"\x02\x00" * 100
    with wave.open(io.BytesIO(stream_header(24000) + pcm)) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (24000, 1, 2)
        assert wav.readframes(100) == pcm

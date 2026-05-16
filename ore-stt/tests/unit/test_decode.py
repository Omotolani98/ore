"""Unit tests for audio decoding (ARCHITECTURE.md §5). No model, no gRPC."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf

from ore_stt.audio.decode import AudioBuffer, DecodeError, decode

_FMT_WAV = 1
_FMT_PCM = 2
_FMT_UNSPECIFIED = 0


def _wav_bytes(samples: np.ndarray, rate: int) -> bytes:
    """Encode a numpy array as 16-bit WAV bytes."""
    buf = io.BytesIO()
    sf.write(buf, samples, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _tone(seconds: float, rate: int) -> np.ndarray:
    """A quiet sine tone, float32 mono in [-1, 1]."""
    t = np.linspace(0.0, seconds, int(seconds * rate), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)


def test_decode_wav_mono() -> None:
    buf = decode(_wav_bytes(_tone(0.5, 16000), 16000), _FMT_WAV, 16000)
    assert isinstance(buf, AudioBuffer)
    assert buf.sample_rate == 16000
    assert buf.samples.dtype == np.float32
    assert buf.samples.ndim == 1
    assert buf.samples.shape == (8000,)
    assert np.all(np.abs(buf.samples) <= 1.0)


def test_decode_wav_stereo_downmix() -> None:
    left = _tone(0.25, 16000)
    right = np.zeros_like(left)
    stereo = np.stack([left, right], axis=1)
    buf = decode(_wav_bytes(stereo, 16000), _FMT_WAV, 16000)
    assert buf.samples.ndim == 1
    # Mean of a channel and silence is half that channel.
    np.testing.assert_allclose(buf.samples, left / 2.0, atol=1e-3)


def test_decode_wav_preserves_rate() -> None:
    buf = decode(_wav_bytes(_tone(0.1, 44100), 44100), _FMT_WAV, 16000)
    assert buf.sample_rate == 44100


def test_decode_pcm_math() -> None:
    # int16 values -> float32 / 32768.0.
    raw = np.array([0, 16384, -32768, 32767], dtype="<i2").tobytes()
    buf = decode(raw, _FMT_PCM, 16000)
    expected = np.array([0.0, 0.5, -1.0, 32767 / 32768.0], dtype=np.float32)
    np.testing.assert_array_equal(buf.samples, expected)
    assert buf.sample_rate == 16000


def test_decode_pcm_odd_length() -> None:
    with pytest.raises(DecodeError, match="multiple of 2"):
        decode(b"\x01\x02\x03", _FMT_PCM, 16000)


@pytest.mark.parametrize("fmt", [_FMT_WAV, _FMT_PCM])
def test_decode_empty_raises(fmt: int) -> None:
    with pytest.raises(DecodeError, match="empty"):
        decode(b"", fmt, 16000)


def test_decode_unsupported_rate() -> None:
    raw = np.zeros(8, dtype="<i2").tobytes()
    with pytest.raises(DecodeError, match="sample rate"):
        decode(raw, _FMT_PCM, 11025)


def test_decode_unknown_format() -> None:
    with pytest.raises(DecodeError, match="format"):
        decode(b"\x00\x00", _FMT_UNSPECIFIED, 16000)


def test_decode_corrupt_wav() -> None:
    with pytest.raises(DecodeError, match="WAV"):
        decode(b"not a real wav file at all", _FMT_WAV, 16000)

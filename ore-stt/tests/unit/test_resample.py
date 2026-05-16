"""Unit tests for resampling (ARCHITECTURE.md §5)."""

from __future__ import annotations

import numpy as np

from ore_stt.audio.resample import TARGET_RATE, resample_to_16k


def _tone(samples: int) -> np.ndarray:
    t = np.linspace(0.0, 1.0, samples, endpoint=False)
    return (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)


def test_resample_noop_16k() -> None:
    audio = _tone(16000)
    out = resample_to_16k(audio, TARGET_RATE)
    np.testing.assert_array_equal(out, audio)


def test_resample_downsamples() -> None:
    audio = _tone(48000)
    out = resample_to_16k(audio, 48000)
    # 48k -> 16k is a 1/3 length reduction.
    assert abs(len(out) - 16000) <= 1


def test_resample_dtype() -> None:
    out = resample_to_16k(_tone(44100), 44100)
    assert out.dtype == np.float32

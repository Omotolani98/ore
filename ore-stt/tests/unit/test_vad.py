"""Unit tests for the silero-vad pre-pass (ARCHITECTURE.md §5)."""

from __future__ import annotations

import numpy as np
import pytest

from ore_stt.audio.vad import SileroVadTrimmer


def test_trimmer_not_ready_before_load() -> None:
    trimmer = SileroVadTrimmer()
    assert trimmer.ready is False


def test_trimmer_rejects_unsupported_rate() -> None:
    with pytest.raises(ValueError):
        SileroVadTrimmer(sample_rate=22050)


def test_trim_called_before_load_raises() -> None:
    trimmer = SileroVadTrimmer()
    with pytest.raises(RuntimeError, match="before load"):
        trimmer.trim(np.zeros(16000, dtype=np.float32))


async def test_trim_returns_empty_on_silence() -> None:
    trimmer = SileroVadTrimmer()
    await trimmer.load()
    assert trimmer.ready is True

    silence = np.zeros(2 * 16000, dtype=np.float32)
    out = trimmer.trim(silence)
    assert out.size == 0


async def test_trim_on_empty_array_is_passthrough() -> None:
    trimmer = SileroVadTrimmer()
    await trimmer.load()
    out = trimmer.trim(np.empty(0, dtype=np.float32))
    assert out.size == 0

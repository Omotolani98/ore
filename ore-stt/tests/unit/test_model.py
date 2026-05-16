"""Unit tests for the model layer (ARCHITECTURE.md §6). No NeMo, no weights."""

from __future__ import annotations

import asyncio
import time

import numpy as np
import pytest

from ore_stt.asr.model import ParakeetModel, QueueTimeoutError, pick_device
from ore_stt.asr.result import TranscriptionResult


def test_pick_device_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_DEVICE", "cuda:7")
    assert pick_device() == "cuda:7"


def test_pick_device_fallback_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    monkeypatch.delenv("STT_DEVICE", raising=False)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    assert pick_device() == "cpu"


async def test_queue_timeout() -> None:
    """A second caller waiting past the timeout while the lock is held raises."""
    model = ParakeetModel("stub", device="cpu", queue_wait_timeout_ms=50)
    model._ready = True

    def slow(audio: np.ndarray, include_timestamps: bool) -> TranscriptionResult:
        time.sleep(0.5)
        return TranscriptionResult(text="ok")

    model._transcribe_blocking = slow  # type: ignore[method-assign]
    audio = np.zeros(16000, dtype=np.float32)

    first = asyncio.create_task(model.transcribe(audio, include_timestamps=False))
    await asyncio.sleep(0.05)  # let `first` acquire the lock

    with pytest.raises(QueueTimeoutError):
        await model.transcribe(audio, include_timestamps=False)

    assert (await first).text == "ok"


async def test_transcribe_before_load_raises() -> None:
    model = ParakeetModel("stub", device="cpu")
    with pytest.raises(RuntimeError, match="before load"):
        await model.transcribe(np.zeros(16000, dtype=np.float32), include_timestamps=False)

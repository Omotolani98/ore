"""Shared pytest fixtures: a stub model and synthetic audio.

Integration tests wire the gRPC servicer with :class:`StubParakeetModel` so they
exercise the request lifecycle without loading NeMo or any weights.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf

# Side-effect import: puts the protoc-generated stubs on sys.path so test
# modules can `from ore.stt.v1 import ...` regardless of import order.
import ore_stt.grpc  # noqa: F401
from ore_stt.asr.result import TranscriptionResult, Word


class StubParakeetModel:
    """Drop-in stand-in for ``ParakeetModel`` returning a canned result.

    Mirrors the async surface the gRPC servicer depends on: ``ready``,
    ``transcribe``, ``load``, ``warmup``.
    """

    def __init__(self, *, ready: bool = True, result: TranscriptionResult | None = None) -> None:
        self._ready = ready
        self.result = result or TranscriptionResult(
            text="hello world",
            words=(Word("hello", 0.0, 0.5), Word("world", 0.5, 1.0)),
            confidence=1.0,
        )

    @property
    def ready(self) -> bool:
        return self._ready

    async def load(self) -> None:
        self._ready = True

    async def warmup(self) -> None:
        return None

    async def transcribe(
        self, audio: np.ndarray, include_timestamps: bool
    ) -> TranscriptionResult:
        if include_timestamps:
            return self.result
        return TranscriptionResult(text=self.result.text, confidence=self.result.confidence)


def _tone(seconds: float, rate: int = 16000) -> np.ndarray:
    """A quiet sine tone, float32 mono in [-1, 1]."""
    t = np.linspace(0.0, seconds, int(seconds * rate), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)


def make_wav_bytes(seconds: float, rate: int = 16000) -> bytes:
    """Encode a ``seconds``-long 16-bit WAV tone as in-memory bytes."""
    buf = io.BytesIO()
    sf.write(buf, _tone(seconds, rate), rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@pytest.fixture
def synthetic_wav() -> bytes:
    """A 1-second 16 kHz WAV — long enough to clear the min-duration floor."""
    return make_wav_bytes(1.0)

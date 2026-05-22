"""Voice-activity-detection pre-pass (ARCHITECTURE.md §5).

When ``trim_silence`` is opt-in on a request, the servicer asks the trimmer to
crop leading/trailing silence so Parakeet only sees speech-active samples. This
is not endpointing and never splits utterances — pre-pass only.

The :class:`SileroVadTrimmer` is the only place that imports ``silero_vad`` or
``torch`` for VAD; everything else depends on the :class:`VadTrimmer` protocol
so tests can substitute a fake without pulling weights.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import numpy as np
from numpy.typing import NDArray

from ore_stt.log import get_logger

if TYPE_CHECKING:
    pass

FloatArray = NDArray[np.float32]

_TARGET_RATE = 16000


class VadTrimmer(Protocol):
    """Pre-pass that crops silence from the head and tail of a mono 16 kHz signal."""

    @property
    def ready(self) -> bool: ...

    def trim(self, samples: FloatArray) -> FloatArray: ...


class SileroVadTrimmer:
    """Silero-VAD-backed implementation of :class:`VadTrimmer`."""

    def __init__(self, sample_rate: int = _TARGET_RATE) -> None:
        if sample_rate != _TARGET_RATE:
            raise ValueError(f"silero-vad pre-pass expects {_TARGET_RATE} Hz, got {sample_rate}")
        self._sample_rate = sample_rate
        self._model: Any = None
        self._ready = False
        self._log = get_logger(__name__)

    @property
    def ready(self) -> bool:
        return self._ready

    async def load(self) -> None:
        """Load the silero-vad model. Idempotent and synchronous under the hood."""
        if self._ready:
            return
        from silero_vad import load_silero_vad

        self._model = load_silero_vad()
        self._ready = True
        self._log.info("vad.load.complete")

    def trim(self, samples: FloatArray) -> FloatArray:
        """Return ``samples`` cropped to the first..last speech-active window.

        Empty input or all-silence input returns a zero-length array. Calling
        before :meth:`load` raises ``RuntimeError``.
        """
        if not self._ready:
            raise RuntimeError("trim called before load")
        if samples.size == 0:
            return samples

        import torch
        from silero_vad import get_speech_timestamps

        tensor = torch.from_numpy(samples)
        segments = get_speech_timestamps(
            tensor,
            self._model,
            sampling_rate=self._sample_rate,
        )
        if not segments:
            return np.empty(0, dtype=np.float32)

        start = int(segments[0]["start"])
        end = int(segments[-1]["end"])
        return np.ascontiguousarray(samples[start:end], dtype=np.float32)

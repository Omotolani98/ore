"""Parakeet model layer (ARCHITECTURE.md §6).

``ParakeetModel`` is the only place in the codebase that imports NeMo. The
import is deferred into :meth:`ParakeetModel.load` so importing this module —
in unit tests, in ``server.py`` — costs nothing and needs no weights.

NeMo's ``transcribe()`` is synchronous and not concurrency-safe, so a single
``asyncio.Lock`` serializes inference and the blocking call runs in the default
executor to keep the event loop responsive.
"""

from __future__ import annotations

import asyncio
import functools
import os
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from ore_stt.asr.result import TranscriptionResult, Word
from ore_stt.log import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

FloatArray = NDArray[np.float32]

_TARGET_RATE = 16000
_WARMUP_SECONDS = 1.0


class QueueTimeoutError(Exception):
    """A transcribe call waited at the model lock longer than the configured timeout."""


def pick_device() -> str:
    """Select an inference device (ARCHITECTURE.md §6.3).

    ``STT_DEVICE`` wins if set; otherwise CUDA, then Apple MPS, then CPU.
    """
    forced = os.environ.get("STT_DEVICE")
    if forced:
        return forced

    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class ParakeetModel:
    """Wraps a resident NeMo Parakeet model behind a small async interface."""

    def __init__(
        self,
        model_name: str,
        device: str | None = None,
        queue_wait_timeout_ms: int = 5000,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._queue_wait_timeout_s = queue_wait_timeout_ms / 1000.0
        self._lock = asyncio.Lock()
        self._model: Any = None
        self._ready = False
        self._log = get_logger(__name__)

    @property
    def ready(self) -> bool:
        """True once weights are loaded and the model can transcribe."""
        return self._ready

    @property
    def device(self) -> str | None:
        """Resolved device, or None until :meth:`load` runs."""
        return self._device

    async def load(self) -> None:
        """Load weights onto the chosen device. Idempotent.

        The blocking ``from_pretrained`` call runs in the default executor so
        the event loop (gRPC + admin HTTP) stays live during the multi-second
        load.
        """
        if self._ready:
            return

        self._device = self._device or pick_device()
        self._log.info(
            "model.load.start", model=self._model_name, device=self._device
        )
        loop = asyncio.get_running_loop()
        self._model = await loop.run_in_executor(None, self._load_blocking)
        self._ready = True
        self._log.info("model.load.complete", model=self._model_name)

    def _load_blocking(self) -> Any:
        """Synchronous weight load. Runs in an executor thread."""
        from nemo.collections.asr.models import ASRModel

        model = ASRModel.from_pretrained(model_name=self._model_name)
        model.to(self._device)
        model.eval()
        return model

    async def warmup(self) -> None:
        """Run one inference on silence so the first real request pays no JIT cost."""
        if not self._ready:
            raise RuntimeError("warmup called before load")
        silence: FloatArray = np.zeros(
            int(_WARMUP_SECONDS * _TARGET_RATE), dtype=np.float32
        )
        await self.transcribe(silence, include_timestamps=False)
        self._log.info("model.warmup.complete")

    async def transcribe(
        self, audio: FloatArray, include_timestamps: bool
    ) -> TranscriptionResult:
        """Transcribe mono float32 16 kHz ``audio``.

        Serialized by the model lock. A wait longer than the configured queue
        timeout raises :class:`QueueTimeoutError`.
        """
        if not self._ready:
            raise RuntimeError("transcribe called before load")

        try:
            await asyncio.wait_for(
                self._lock.acquire(), timeout=self._queue_wait_timeout_s
            )
        except TimeoutError as exc:
            raise QueueTimeoutError(
                f"waited over {self._queue_wait_timeout_s:.1f}s at the model lock"
            ) from exc

        try:
            loop = asyncio.get_running_loop()
            run: Callable[[], Any] = functools.partial(
                self._transcribe_blocking, audio, include_timestamps
            )
            return await loop.run_in_executor(None, run)
        finally:
            self._lock.release()

    def _transcribe_blocking(
        self, audio: FloatArray, include_timestamps: bool
    ) -> TranscriptionResult:
        """Synchronous NeMo inference + result mapping. Runs in an executor thread."""
        hypotheses = self._model.transcribe(
            [audio],
            batch_size=1,
            timestamps=include_timestamps,
            verbose=False,
        )
        return _map_hypothesis(hypotheses[0], include_timestamps)


def _map_hypothesis(hyp: Any, include_timestamps: bool) -> TranscriptionResult:
    """Map a NeMo hypothesis (or bare string) into a :class:`TranscriptionResult`."""
    text = hyp if isinstance(hyp, str) else getattr(hyp, "text", "")

    words: tuple[Word, ...] = ()
    if include_timestamps and not isinstance(hyp, str):
        stamp = getattr(hyp, "timestamp", None) or {}
        words = tuple(
            Word(
                text=str(w.get("word", "")),
                start_sec=float(w.get("start", 0.0)),
                end_sec=float(w.get("end", 0.0)),
            )
            for w in stamp.get("word", [])
        )

    confidence = 0.0 if not text else 1.0
    return TranscriptionResult(text=text, words=words, confidence=confidence)

"""ASR result value types (ARCHITECTURE.md §6).

Frozen dataclasses so the model layer hands the gRPC layer an immutable result
that is independent of NeMo's own hypothesis objects. The gRPC service maps
these into the proto ``TranscribeResponse``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Word:
    """One transcribed word with its time span, in seconds from audio start."""

    text: str
    start_sec: float
    end_sec: float


@dataclass(frozen=True)
class TranscriptionResult:
    """A complete transcription: text, optional word timings, and confidence.

    ``words`` is empty when the caller did not request timestamps. ``confidence``
    is in ``[0.0, 1.0]``; an empty transcript carries ``0.0``.
    """

    text: str
    words: tuple[Word, ...] = field(default_factory=tuple)
    confidence: float = 0.0

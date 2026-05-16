"""Audio decoding (ARCHITECTURE.md §5): WAV / PCM_S16LE bytes -> float32 mono.

This layer is pure and gRPC-free. It raises :class:`DecodeError` on bad input;
the gRPC service (S5) maps that to ``INVALID_ARGUMENT``. The decoded buffer is
mono float32 in ``[-1.0, 1.0]`` but keeps its native sample rate — resampling to
16 kHz is a separate step (:mod:`ore_stt.audio.resample`).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from ore_stt.log import get_logger

# Canonical decoded-audio array: mono float32.
FloatArray = NDArray[np.float32]

# Proto AudioFormat enum values (proto/ore/stt/v1/stt.proto).
_FORMAT_WAV = 1
_FORMAT_PCM_S16LE = 2

# Sample rates the service accepts (ARCHITECTURE.md §4.3).
_SUPPORTED_RATES: frozenset[int] = frozenset({8000, 16000, 22050, 44100, 48000})

_PCM_FULL_SCALE = 32768.0


class DecodeError(Exception):
    """Audio could not be decoded: empty, corrupt, or an unsupported rate/format."""


@dataclass(frozen=True)
class AudioBuffer:
    """Decoded audio: mono float32 samples paired with their native sample rate."""

    samples: FloatArray
    sample_rate: int


def decode(audio: bytes, fmt: int, sample_rate: int) -> AudioBuffer:
    """Decode ``audio`` of the given proto ``AudioFormat`` into an :class:`AudioBuffer`.

    ``sample_rate`` is required for PCM (the raw stream carries no header) and is
    ignored for WAV (the file header is authoritative).
    """
    if not audio:
        raise DecodeError("audio is empty")

    if fmt == _FORMAT_WAV:
        samples, rate = _decode_wav(audio)
    elif fmt == _FORMAT_PCM_S16LE:
        samples, rate = _decode_pcm(audio, sample_rate), sample_rate
    else:
        raise DecodeError(f"unsupported audio format: {fmt}")

    if rate not in _SUPPORTED_RATES:
        raise DecodeError(f"unsupported sample rate: {rate}")

    return AudioBuffer(samples=samples, sample_rate=rate)


def _decode_wav(audio: bytes) -> tuple[FloatArray, int]:
    """Parse WAV bytes via soundfile; downmix to mono if multi-channel."""
    try:
        samples, rate = sf.read(io.BytesIO(audio), dtype="float32", always_2d=False)
    except (sf.LibsndfileError, RuntimeError, ValueError) as exc:
        raise DecodeError(f"corrupt or unreadable WAV: {exc}") from exc

    if samples.ndim > 1:
        samples = _downmix(samples)
    return np.ascontiguousarray(samples, dtype=np.float32), int(rate)


def _decode_pcm(audio: bytes, sample_rate: int) -> FloatArray:
    """Decode raw little-endian signed 16-bit PCM. Mono only (ARCHITECTURE.md §5)."""
    if len(audio) % 2 != 0:
        raise DecodeError("PCM_S16LE byte length is not a multiple of 2")
    pcm = np.frombuffer(audio, dtype="<i2")
    return (pcm.astype(np.float32) / _PCM_FULL_SCALE).copy()


def _downmix(samples: FloatArray) -> FloatArray:
    """Average channels into a single mono track. Stereo input is not rejected (§5)."""
    get_logger(__name__).warning("audio.downmix", channels=samples.shape[1])
    mono: FloatArray = samples.mean(axis=1, dtype=np.float32)
    return mono

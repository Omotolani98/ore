"""Resampling (ARCHITECTURE.md §5): bring decoded audio to the model's 16 kHz.

Parakeet expects 16 kHz. The common case — input already at 16 kHz — skips
resampling entirely; only off-rate audio pays the cost.
"""

from __future__ import annotations

import librosa
import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float32]

TARGET_RATE = 16000


def resample_to_16k(samples: FloatArray, src_rate: int) -> FloatArray:
    """Resample mono float32 ``samples`` from ``src_rate`` to 16 kHz.

    Returns the input unchanged when it is already at 16 kHz.
    """
    if src_rate == TARGET_RATE:
        return samples
    resampled = librosa.resample(samples, orig_sr=src_rate, target_sr=TARGET_RATE)
    return np.ascontiguousarray(resampled, dtype=np.float32)

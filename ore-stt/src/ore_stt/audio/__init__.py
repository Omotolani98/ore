"""Audio pipeline: decode, resample, optional VAD trim."""

from ore_stt.audio.vad import SileroVadTrimmer, VadTrimmer

__all__ = ["SileroVadTrimmer", "VadTrimmer"]

"""End-to-end transcription against the real Parakeet model (ARCHITECTURE.md §11).

Marked ``e2e``: excluded from ``make test``, run manually or on a GPU runner.
Skipped until real-speech fixture WAVs are dropped into ``tests/fixtures/``.
WER-against-expected assertions are S8; here we only assert non-empty text.
"""

from __future__ import annotations

import pathlib

import pytest

from ore_stt.asr.model import ParakeetModel
from ore_stt.audio.decode import decode
from ore_stt.audio.resample import resample_to_16k

pytestmark = pytest.mark.e2e

_FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
_FMT_WAV = 1


@pytest.mark.parametrize("name", ["hello.wav", "long.wav"])
async def test_transcribe_fixture(name: str) -> None:
    wav_path = _FIXTURES / name
    if not wav_path.exists():
        pytest.skip(f"fixture {name} not present")

    model = ParakeetModel("nvidia/parakeet-tdt-0.6b-v2")
    await model.load()
    await model.warmup()

    buffer = decode(wav_path.read_bytes(), _FMT_WAV, 16000)
    samples = resample_to_16k(buffer.samples, buffer.sample_rate)
    result = await model.transcribe(samples, include_timestamps=True)

    assert result.text.strip(), "expected a non-empty transcript"

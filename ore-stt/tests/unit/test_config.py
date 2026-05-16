"""Unit tests for Settings (ARCHITECTURE.md §8)."""

import pytest

from ore_stt.config import Settings


def test_defaults() -> None:
    s = Settings()
    assert s.grpc_host == "127.0.0.1"
    assert s.grpc_port == 50051
    assert s.admin_host == "127.0.0.1"
    assert s.admin_port == 8080
    assert s.model_name == "nvidia/parakeet-tdt-0.6b-v2"
    assert s.device is None
    assert s.max_audio_seconds == 120.0
    assert s.min_audio_seconds == 0.25
    assert s.queue_wait_timeout_ms == 5000
    assert s.vad_default is False
    assert s.log_level == "INFO"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_GRPC_PORT", "60000")
    monkeypatch.setenv("STT_VAD_DEFAULT", "true")
    monkeypatch.setenv("STT_DEVICE", "cpu")
    s = Settings()
    assert s.grpc_port == 60000
    assert s.vad_default is True
    assert s.device == "cpu"

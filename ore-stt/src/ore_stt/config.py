"""Environment-driven configuration (ARCHITECTURE.md §8).

``Settings`` is the single source of truth. Nothing else reads ``os.environ``.
All variables are prefixed ``STT_``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration, populated from ``STT_*`` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="STT_",
        extra="ignore",
        protected_namespaces=(),  # allow the `model_name` field
    )

    grpc_host: str = "127.0.0.1"
    grpc_port: int = 50051
    admin_host: str = "127.0.0.1"
    admin_port: int = 8080

    model_name: str = "nvidia/parakeet-tdt-0.6b-v2"
    device: str | None = None

    max_audio_seconds: float = 120.0
    min_audio_seconds: float = 0.25
    queue_wait_timeout_ms: int = 5000
    vad_default: bool = False

    log_level: str = "INFO"

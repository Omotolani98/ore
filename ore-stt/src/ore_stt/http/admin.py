"""Admin HTTP surface (ARCHITECTURE.md §7): /healthz, /readyz, /info.

Liveness and readiness only. No POST, no mutations — anything that changes
state goes through gRPC or a process restart.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ore_stt.config import Settings


def create_admin_app(settings: Settings, is_ready: Callable[[], bool]) -> FastAPI:
    """Build the admin FastAPI app.

    ``is_ready`` is the readiness probe. In v1 it is backed by a dummy flag;
    once the model layer lands (S4) it becomes ``lambda: model.ready`` with no
    change here.
    """
    app = FastAPI(title="ore-stt admin", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Process liveness. Never depends on model state."""
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        """Model readiness. 503 until the model is loaded."""
        if is_ready():
            return JSONResponse({"status": "ready", "model": settings.model_name})
        return JSONResponse({"status": "loading"}, status_code=503)

    @app.get("/info")
    async def info() -> dict[str, object]:
        """Ops metadata. Not for hot-path use."""
        return {
            "model": settings.model_name,
            "device": settings.device or "auto",
            "max_audio_seconds": settings.max_audio_seconds,
            "queue_depth": 0,  # real depth lands with the model lock (S4)
        }

    return app

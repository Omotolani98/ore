"""Admin HTTP surface tests (ARCHITECTURE.md §7).

Drives the FastAPI app over an in-memory ASGI transport with a controllable
readiness probe — no gRPC server, no model.
"""

from __future__ import annotations

import httpx

from ore_stt.config import Settings
from ore_stt.http.admin import create_admin_app


def _client(*, ready: bool) -> httpx.AsyncClient:
    app = create_admin_app(Settings(), lambda: ready)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://admin",
    )


async def test_healthz_ok() -> None:
    async with _client(ready=False) as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_loading() -> None:
    async with _client(ready=False) as client:
        resp = await client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "loading"}


async def test_readyz_ready() -> None:
    async with _client(ready=True) as client:
        resp = await client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["model"] == Settings().model_name


async def test_info_shape() -> None:
    async with _client(ready=True) as client:
        resp = await client.get("/info")
    assert resp.status_code == 200
    body = resp.json()
    settings = Settings()
    assert body["model"] == settings.model_name
    assert body["max_audio_seconds"] == settings.max_audio_seconds
    assert body["queue_depth"] == 0
    assert "device" in body

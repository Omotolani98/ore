"""Process entry point: runs the gRPC server and the admin HTTP server.

Both run in one process on one event loop (ARCHITECTURE.md §2): one resident
Parakeet model dominates memory and NeMo's ``transcribe()`` is not concurrency
-safe, so there is no multi-worker split. The model loads eagerly in a
background task at startup; ``/readyz`` and gRPC stay unready until it lands.
"""

from __future__ import annotations

import asyncio
import signal

import grpc
import uvicorn

from ore_stt.asr.model import ParakeetModel
from ore_stt.audio.vad import SileroVadTrimmer
from ore_stt.config import Settings
from ore_stt.grpc.service import SpeechToTextServicer
from ore_stt.http.admin import create_admin_app
from ore_stt.log import configure_logging, get_logger

# Default 4 MB is too small for a 2-minute WAV (ARCHITECTURE.md §14).
_MAX_MESSAGE_BYTES = 16 * 1024 * 1024


async def _load_and_warmup(model: ParakeetModel, vad: SileroVadTrimmer) -> None:
    """Load model weights then run a warmup inference (ARCHITECTURE.md §6.1).

    The VAD model loads alongside Parakeet so the first opt-in request pays no
    setup cost (ARCHITECTURE.md §5).
    """
    log = get_logger(__name__)
    try:
        await model.load()
        await model.warmup()
    except Exception:
        # Log and leave the model unready; /readyz and gRPC stay UNAVAILABLE.
        log.exception("model.load.failed")
    try:
        await vad.load()
    except Exception:
        # VAD failure is non-fatal: trim_silence requests fall back to raw audio.
        log.exception("vad.load.failed")


async def serve(settings: Settings) -> None:
    """Start the gRPC and admin servers; block until SIGINT/SIGTERM."""
    log = get_logger(__name__)

    # Imported here so a missing `make proto` fails loudly at startup, not import time.
    from ore.stt.v1 import stt_pb2_grpc

    model = ParakeetModel(settings.model_name, settings.device, settings.queue_wait_timeout_ms)
    vad = SileroVadTrimmer()

    grpc_server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", _MAX_MESSAGE_BYTES),
            ("grpc.max_receive_message_length", _MAX_MESSAGE_BYTES),
        ]
    )
    stt_pb2_grpc.add_SpeechToTextServicer_to_server(
        SpeechToTextServicer(model, settings, vad=vad), grpc_server
    )

    grpc_bind = f"{settings.grpc_host}:{settings.grpc_port}"
    grpc_server.add_insecure_port(grpc_bind)
    await grpc_server.start()
    log.info("server.started", bind=grpc_bind)

    admin_app = create_admin_app(settings, lambda: model.ready)
    admin = uvicorn.Server(
        uvicorn.Config(
            admin_app,
            host=settings.admin_host,
            port=settings.admin_port,
            log_config=None,  # structlog is the only log source (ARCHITECTURE.md §9)
            access_log=False,
        )
    )
    admin_task = asyncio.create_task(admin.serve())
    log.info("admin.started", bind=f"{settings.admin_host}:{settings.admin_port}")

    load_task = asyncio.create_task(_load_and_warmup(model, vad))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    log.info("server.stopping")

    load_task.cancel()
    admin.should_exit = True
    await admin_task
    await grpc_server.stop(grace=5.0)


def main() -> None:
    """CLI entry point invoked by ``python -m ore_stt``."""
    settings = Settings()
    configure_logging(settings.log_level)
    asyncio.run(serve(settings))

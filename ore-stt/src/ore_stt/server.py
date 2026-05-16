"""Process entry point. S1: starts a no-op gRPC server.

Admin HTTP (FastAPI) and the model are wired in later milestones (S2, S4).
"""

from __future__ import annotations

import asyncio
import signal

import grpc

from ore_stt.config import Settings
from ore_stt.grpc.service import SpeechToTextServicer
from ore_stt.log import configure_logging, get_logger

# Default 4 MB is too small for a 2-minute WAV (ARCHITECTURE.md §14).
_MAX_MESSAGE_BYTES = 16 * 1024 * 1024


async def serve(settings: Settings) -> None:
    """Start the gRPC server and block until SIGINT/SIGTERM."""
    log = get_logger(__name__)

    # Imported here so a missing `make proto` fails loudly at startup, not import time.
    from ore.stt.v1 import stt_pb2_grpc

    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", _MAX_MESSAGE_BYTES),
            ("grpc.max_receive_message_length", _MAX_MESSAGE_BYTES),
        ]
    )
    stt_pb2_grpc.add_SpeechToTextServicer_to_server(SpeechToTextServicer(), server)

    bind = f"{settings.grpc_host}:{settings.grpc_port}"
    server.add_insecure_port(bind)
    await server.start()
    log.info("server.started", bind=bind)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    log.info("server.stopping")
    await server.stop(grace=5.0)


def main() -> None:
    """CLI entry point invoked by ``python -m ore_stt``."""
    settings = Settings()
    configure_logging(settings.log_level)
    asyncio.run(serve(settings))

"""SpeechToText servicer. S1 skeleton: every RPC returns UNIMPLEMENTED."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, NoReturn

import grpc

try:
    from ore.stt.v1 import stt_pb2, stt_pb2_grpc
except ImportError as exc:  # pragma: no cover
    raise ImportError("gRPC stubs not found. Run `make proto` before starting the server.") from exc

_Servicer: Any = stt_pb2_grpc.SpeechToTextServicer


class SpeechToTextServicer(_Servicer):  # type: ignore[misc]
    """All handlers stubbed for S1. Real transcription lands in S4."""

    async def Transcribe(
        self,
        request: stt_pb2.TranscribeRequest,
        context: grpc.aio.ServicerContext,
    ) -> NoReturn:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED, "Transcribe not implemented (S1 skeleton)"
        )
        raise AssertionError("unreachable")  # context.abort never returns

    async def TranscribeStream(
        self,
        request_iterator: AsyncIterator[stt_pb2.AudioChunk],
        context: grpc.aio.ServicerContext,
    ) -> NoReturn:
        # Streaming is deliberately UNIMPLEMENTED in v1 (ARCHITECTURE.md §4.2).
        await context.abort(grpc.StatusCode.UNIMPLEMENTED, "TranscribeStream not implemented (v1)")
        raise AssertionError("unreachable")

"""SpeechToText servicer.

The ``Transcribe`` handler runs the happy path: validate readiness, decode,
resample, transcribe, respond. Exhaustive gRPC error-code coverage is S5; this
handler maps the obvious failures — model not ready, decode failure, queue
timeout, inference error. ``TranscribeStream`` stays ``UNIMPLEMENTED`` (§4.2).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, NoReturn

import grpc
from ulid import ULID

from ore_stt.asr.model import ParakeetModel, QueueTimeoutError
from ore_stt.audio.decode import DecodeError, decode
from ore_stt.audio.resample import TARGET_RATE, resample_to_16k
from ore_stt.log import get_logger

if TYPE_CHECKING:
    from ore_stt.config import Settings

try:
    from ore.stt.v1 import stt_pb2, stt_pb2_grpc
except ImportError as exc:  # pragma: no cover
    raise ImportError("gRPC stubs not found. Run `make proto` before starting the server.") from exc

_Servicer: Any = stt_pb2_grpc.SpeechToTextServicer


class SpeechToTextServicer(_Servicer):  # type: ignore[misc]
    """Implements the SpeechToText gRPC service over a resident Parakeet model."""

    def __init__(self, model: ParakeetModel, settings: Settings) -> None:
        self._model = model
        self._settings = settings
        self._log = get_logger(__name__)

    async def Transcribe(
        self,
        request: stt_pb2.TranscribeRequest,
        context: grpc.aio.ServicerContext,
    ) -> stt_pb2.TranscribeResponse:
        request_id = request.request_id or str(ULID())
        started = time.monotonic()

        if not self._model.ready:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "model is still loading")
            raise AssertionError("unreachable")

        self._log.info(
            "request.received",
            request_id=request_id,
            audio_bytes=len(request.audio),
            format=int(request.format),
        )

        try:
            buffer = decode(request.audio, int(request.format), request.sample_rate)
        except DecodeError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
            raise AssertionError("unreachable") from exc

        samples = resample_to_16k(buffer.samples, buffer.sample_rate)
        duration_s = len(samples) / TARGET_RATE
        self._log.info(
            "audio.decoded",
            request_id=request_id,
            duration_ms=round(duration_s * 1000),
            sample_rate=buffer.sample_rate,
        )

        if duration_s > self._settings.max_audio_seconds:
            await context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                f"audio exceeds max {self._settings.max_audio_seconds}s",
            )
            raise AssertionError("unreachable")

        if duration_s < self._settings.min_audio_seconds:
            # Too short to be speech (§5.1): empty transcript, not an error.
            return _build_response("", (), 0.0, request_id, started, duration_s)

        try:
            result = await self._model.transcribe(
                samples, include_timestamps=request.include_timestamps
            )
        except QueueTimeoutError as exc:
            await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, str(exc))
            raise AssertionError("unreachable") from exc
        except Exception as exc:
            # Any inference failure maps to INTERNAL (ARCHITECTURE.md §4.2).
            self._log.error("inference.failed", request_id=request_id, error=str(exc))
            await context.abort(grpc.StatusCode.INTERNAL, "transcription failed")
            raise AssertionError("unreachable") from exc

        self._log.info("inference.done", request_id=request_id, chars=len(result.text))
        response = _build_response(
            result.text, result.words, result.confidence, request_id, started, duration_s
        )
        self._log.info(
            "request.completed",
            request_id=request_id,
            latency_ms=response.latency_ms,
            chars=len(result.text),
        )
        return response

    async def TranscribeStream(
        self,
        request_iterator: AsyncIterator[stt_pb2.AudioChunk],
        context: grpc.aio.ServicerContext,
    ) -> NoReturn:
        # Streaming is deliberately UNIMPLEMENTED in v1 (ARCHITECTURE.md §4.2).
        await context.abort(grpc.StatusCode.UNIMPLEMENTED, "TranscribeStream not implemented (v1)")
        raise AssertionError("unreachable")


def _build_response(
    text: str,
    words: tuple[Any, ...],
    confidence: float,
    request_id: str,
    started: float,
    duration_s: float,
) -> stt_pb2.TranscribeResponse:
    """Assemble a ``TranscribeResponse`` from a transcription result."""
    return stt_pb2.TranscribeResponse(
        text=text,
        words=[stt_pb2.Word(text=w.text, start_sec=w.start_sec, end_sec=w.end_sec) for w in words],
        confidence=confidence,
        latency_ms=round((time.monotonic() - started) * 1000),
        request_id=request_id,
        audio_duration_ms=round(duration_s * 1000),
    )

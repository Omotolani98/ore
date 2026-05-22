"""gRPC handler tests (ARCHITECTURE.md §11).

Drives a real ``grpc.aio`` server on an ephemeral port with the servicer wired
to a stub model — exercises the request lifecycle, not NeMo.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import grpc
import pytest
from conftest import StubParakeetModel, make_stereo_wav_bytes, make_wav_bytes
from ore.stt.v1 import stt_pb2, stt_pb2_grpc

from ore_stt.asr.model import QueueTimeoutError
from ore_stt.asr.result import TranscriptionResult
from ore_stt.config import Settings
from ore_stt.grpc.service import SpeechToTextServicer


@asynccontextmanager
async def _stub_for(
    model: StubParakeetModel,
    settings: Settings | None = None,
) -> AsyncIterator[stt_pb2_grpc.SpeechToTextStub]:
    """Run a server backed by ``model`` and yield a connected client stub."""
    server = grpc.aio.server()
    stt_pb2_grpc.add_SpeechToTextServicer_to_server(
        SpeechToTextServicer(model, settings or Settings()),
        server,  # type: ignore[arg-type]
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield stt_pb2_grpc.SpeechToTextStub(channel)
    finally:
        await channel.close()
        await server.stop(grace=None)


def _request(audio: bytes, **kw: object) -> stt_pb2.TranscribeRequest:
    defaults: dict[str, object] = {
        "audio": audio,
        "format": stt_pb2.AUDIO_FORMAT_WAV,
        "sample_rate": 16000,
        "include_timestamps": True,
    }
    defaults.update(kw)
    return stt_pb2.TranscribeRequest(**defaults)  # type: ignore[arg-type]


async def test_transcribe_returns_text() -> None:
    async with _stub_for(StubParakeetModel()) as stub:
        resp = await stub.Transcribe(_request(make_wav_bytes(1.0)))
    assert resp.text == "hello world"
    assert [w.text for w in resp.words] == ["hello", "world"]
    assert resp.confidence == 1.0
    assert resp.request_id
    assert resp.audio_duration_ms == pytest.approx(1000, abs=2)


async def test_transcribe_propagates_request_id() -> None:
    async with _stub_for(StubParakeetModel()) as stub:
        resp = await stub.Transcribe(_request(make_wav_bytes(1.0), request_id="rid-123"))
    assert resp.request_id == "rid-123"


async def test_transcribe_model_not_ready() -> None:
    async with _stub_for(StubParakeetModel(ready=False)) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(_request(make_wav_bytes(1.0)))
    assert exc.value.code() == grpc.StatusCode.UNAVAILABLE


async def test_transcribe_empty_audio() -> None:
    async with _stub_for(StubParakeetModel()) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(_request(b""))
    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_transcribe_corrupt_wav() -> None:
    async with _stub_for(StubParakeetModel()) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(_request(b"not a real wav at all"))
    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_transcribe_below_min_duration() -> None:
    # 0.1 s is under the 0.25 s floor (§5.1): empty transcript, not an error.
    async with _stub_for(StubParakeetModel()) as stub:
        resp = await stub.Transcribe(_request(make_wav_bytes(0.1)))
    assert resp.text == ""
    assert resp.confidence == 0.0


async def test_transcribe_inference_error() -> None:
    class Boom(StubParakeetModel):
        async def transcribe(self, audio: object, include_timestamps: bool) -> TranscriptionResult:
            raise RuntimeError("model exploded")

    async with _stub_for(Boom()) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(_request(make_wav_bytes(1.0)))
    assert exc.value.code() == grpc.StatusCode.INTERNAL


async def test_transcribe_stream_unimplemented() -> None:
    async with _stub_for(StubParakeetModel()) as stub:
        call = stub.TranscribeStream(iter([stt_pb2.AudioChunk()]))
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await call.read()
    assert exc.value.code() == grpc.StatusCode.UNIMPLEMENTED


async def test_transcribe_unsupported_format() -> None:
    # AUDIO_FORMAT_UNSPECIFIED (0) is not a decodable format (§4.2/§4.3).
    async with _stub_for(StubParakeetModel()) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(
                _request(make_wav_bytes(1.0), format=stt_pb2.AUDIO_FORMAT_UNSPECIFIED)
            )
    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "format" in exc.value.details()


async def test_transcribe_unsupported_sample_rate() -> None:
    # 11025 is outside the allowed set {8000,16000,22050,44100,48000} (§4.3).
    pcm = b"\x00\x00" * 16000  # 1s of zeros, mono, irrelevant rate at decode
    async with _stub_for(StubParakeetModel()) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(
                _request(pcm, format=stt_pb2.AUDIO_FORMAT_PCM_S16LE, sample_rate=11025)
            )
    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_transcribe_pcm_odd_byte_length() -> None:
    # PCM_S16LE must have even byte length (2 bytes per sample).
    async with _stub_for(StubParakeetModel()) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(_request(b"\x00\x01\x02", format=stt_pb2.AUDIO_FORMAT_PCM_S16LE))
    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_transcribe_audio_too_long() -> None:
    # Audio longer than configured max → RESOURCE_EXHAUSTED (§4.2).
    settings = Settings(max_audio_seconds=1.0)
    audio = make_wav_bytes(1.5)
    async with _stub_for(StubParakeetModel(), settings=settings) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(_request(audio))
    assert exc.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED


async def test_transcribe_queue_timeout() -> None:
    class Backpressure(StubParakeetModel):
        async def transcribe(self, audio: object, include_timestamps: bool) -> TranscriptionResult:
            raise QueueTimeoutError("queue is full")

    async with _stub_for(Backpressure()) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(_request(make_wav_bytes(1.0)))
    assert exc.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED


async def test_transcribe_cancelled_by_client() -> None:
    class Slow(StubParakeetModel):
        async def transcribe(self, audio: object, include_timestamps: bool) -> TranscriptionResult:
            await asyncio.sleep(5.0)
            raise AssertionError("unreachable")

    async with _stub_for(Slow()) as stub:
        call = stub.Transcribe(_request(make_wav_bytes(1.0)))
        await asyncio.sleep(0.1)
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
        assert await call.code() == grpc.StatusCode.CANCELLED


async def test_transcribe_stereo_downmixes() -> None:
    # Stereo input is downmixed, not rejected (§4.3 rule 5).
    async with _stub_for(StubParakeetModel()) as stub:
        resp = await stub.Transcribe(_request(make_stereo_wav_bytes(1.0)))
    assert resp.text == "hello world"
    assert resp.audio_duration_ms == pytest.approx(1000, abs=2)


async def test_validation_order_format_before_empty() -> None:
    # §4.3: format is checked before empty audio. With both invalid, the error
    # message should mention format, not emptiness.
    async with _stub_for(StubParakeetModel()) as stub:
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.Transcribe(_request(b"", format=stt_pb2.AUDIO_FORMAT_UNSPECIFIED))
    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "format" in exc.value.details()

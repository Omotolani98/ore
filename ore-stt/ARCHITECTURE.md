# ore-stt — Architecture

**Status:** Draft v0.1
**Author:** Omotolani
**Last updated:** 2026-05-16
**Parent spec:** `ore-spec.md` v0.2

---

## 1. Purpose

`ore-stt` is the speech-to-text service for the Ore agent system. It is a long-running daemon that:

1. Loads NVIDIA Parakeet TDT 0.6B v2 once at startup, keeps weights resident.
2. Accepts audio over gRPC, transcribes it, and returns text plus word-level timestamps.
3. Exposes a small HTTP surface for health and readiness checks.

It is the only Python service in the Ore stack. Everything else is Go. The boundary is gRPC — `ore-stt` has no knowledge of the agent, the tool registry, or the LLM. Its single responsibility is _audio bytes → transcript_.

**Out of scope for ore-stt:**

- Voice activity detection beyond an optional trimming pre-pass.
- Wake-word detection.
- Speaker diarization.
- Translation or language detection (English only by design).
- Audio file format conversion beyond the two accepted formats (WAV, PCM_S16LE). Anything else is the caller's problem.
- TTS, sentiment, emotion, or any non-transcription audio analysis.

---

## 2. Stack

| Concern             | Choice                                                                | Rationale                                                                                             |
| ------------------- | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Language            | Python 3.11                                                           | Required by `nemo-toolkit`. 3.12+ has historical NeMo issues; pin to 3.11 until upstream catches up.  |
| Dependency manager  | `uv`                                                                  | Fast, reproducible, lockfile-first. Replaces pip + venv + pip-tools in one tool.                      |
| Linter / formatter  | `ruff`                                                                | Single binary covers lint + format. No `black`, no `isort`, no `flake8`.                              |
| Type checker        | `mypy` (strict mode)                                                  | Catches surface-level mistakes; gRPC stubs are typed so the boundary stays honest.                    |
| ASR model           | `nvidia/parakeet-tdt-0.6b-v2`                                         | English-only by user choice. SOTA on Open ASR Leaderboard, fast on CPU and GPU.                       |
| ASR runtime         | `nemo-toolkit[asr]`                                                   | Official NVIDIA toolkit. The path of least resistance for Parakeet today.                             |
| Audio decoding      | `soundfile` + `numpy`                                                 | `soundfile` handles WAV; raw PCM is decoded directly via `numpy.frombuffer`.                          |
| Optional VAD        | `silero-vad` (torch)                                                  | Optional, off by default. Used only for silence trimming, not endpointing.                            |
| gRPC                | `grpcio` + `grpcio-tools`                                             | Standard Python gRPC. Async server.                                                                   |
| Admin HTTP          | `fastapi` + `uvicorn`                                                 | Just for `/healthz` and `/readyz`. No business logic.                                                 |
| Logging             | `structlog`                                                           | JSON logs to stdout. Single source of structured logging across the codebase.                         |
| Process supervision | Native — `uvicorn` runs FastAPI in-process, gRPC runs in same process | One process, one model. No multi-worker contortions; Parakeet isn't thread-safe at the wrapper layer. |
| Container base      | `python:3.11-slim` + `ffmpeg` apt package                             | `ffmpeg` only present because some NeMo audio paths shell out to it.                                  |
| Testing             | `pytest`, `pytest-asyncio`, `grpcio-testing`                          | Async-aware test runner; gRPC test channel for handler-level tests.                                   |
| CI                  | GitHub Actions                                                        | Lint → typecheck → test → build image.                                                                |

**Notable non-choices:**

- **Not `poetry`.** `uv` is faster, integrates with PEP 621 `pyproject.toml` cleanly, and has better lockfile semantics for reproducible builds.
- **Not `whisper.cpp` / `faster-whisper`.** Parakeet is faster for English and the user explicitly chose it. We do not include a fallback ASR — single model, single responsibility.
- **Not multi-worker gRPC.** A single resident model dominates memory; running two workers doubles the RAM cost. Concurrency is handled by an `asyncio.Lock` inside one process.
- **Not ONNX export.** NeMo's TDT decoder doesn't export cleanly to ONNX today. Stay on the native PyTorch path until that changes.

---

## 3. Component Layout

```
ore-stt/
├── pyproject.toml             # uv-managed, PEP 621
├── uv.lock
├── README.md
├── Dockerfile
├── .ruff.toml
├── mypy.ini
├── Makefile                   # entry points: dev, lint, typecheck, test, proto, run
├── proto/
│   └── ore/stt/v1/
│       └── stt.proto          # source of truth, shared with the Go agent
├── src/
│   └── ore_stt/
│       ├── __init__.py
│       ├── __main__.py        # python -m ore_stt
│       ├── config.py          # env-driven config (pydantic-settings)
│       ├── server.py          # process entry: starts gRPC + FastAPI together
│       ├── log.py             # structlog setup
│       ├── audio/
│       │   ├── __init__.py
│       │   ├── decode.py      # WAV / PCM decode -> numpy float32 @ 16kHz
│       │   ├── resample.py    # if a future client sends non-16k audio
│       │   └── vad.py         # optional silero-vad wrapper
│       ├── asr/
│       │   ├── __init__.py
│       │   ├── model.py       # ParakeetModel: load, warm, transcribe
│       │   └── result.py      # ASR result types (frozen dataclasses)
│       ├── grpc/
│       │   ├── __init__.py
│       │   ├── service.py     # SpeechToTextServicer implementation
│       │   ├── interceptors.py# request-id, logging, error mapping
│       │   └── generated/     # protoc output (gitignored, regenerated)
│       └── http/
│           ├── __init__.py
│           └── admin.py       # FastAPI app for /healthz, /readyz
└── tests/
    ├── conftest.py            # shared fixtures (model stub, sample WAV)
    ├── fixtures/
    │   ├── hello.wav          # short sample audio
    │   └── long.wav
    ├── unit/
    │   ├── test_decode.py
    │   ├── test_vad.py
    │   └── test_config.py
    └── integration/
        ├── test_grpc.py       # full handler tests over an in-memory channel
        └── test_admin.py
```

**Rules:**

- All source code under `src/ore_stt/`. No flat-layout. `src/`-layout prevents the classic "tests pick up the wrong package" footgun.
- Generated gRPC code goes under `src/ore_stt/grpc/generated/` and is gitignored. CI and `make proto` regenerate it.
- `proto/` lives at the repo root so the Go side can `git submodule` it (or vendor it) without reaching into a Python source tree.

---

## 4. gRPC Contract

The `.proto` is the API. Both this service and the Go agent import from it.

### 4.1 Service definition

```protobuf
syntax = "proto3";
package ore.stt.v1;

option go_package = "ore/proto/ore/stt/v1;sttv1";

service SpeechToText {
  // Batch transcription. Audio sent in a single request.
  rpc Transcribe(TranscribeRequest) returns (TranscribeResponse);

  // Phase 1.5 - streaming variant. Stub the handler for now,
  // return UNIMPLEMENTED until we actually need it.
  rpc TranscribeStream(stream AudioChunk) returns (stream TranscribeEvent);
}

message TranscribeRequest {
  bytes audio = 1;
  AudioFormat format = 2;
  uint32 sample_rate = 3;       // expected: 16000; anything else triggers resample.
  bool include_timestamps = 4;
  string request_id = 5;        // optional; server generates if empty.
  bool trim_silence = 6;        // opt-in VAD pre-pass.
}

message TranscribeResponse {
  string text = 1;
  repeated Word words = 2;
  float confidence = 3;
  uint64 latency_ms = 4;
  string request_id = 5;
  uint32 audio_duration_ms = 6;
}

message Word {
  string text = 1;
  float start_sec = 2;
  float end_sec = 3;
}

enum AudioFormat {
  AUDIO_FORMAT_UNSPECIFIED = 0;
  AUDIO_FORMAT_WAV         = 1;
  AUDIO_FORMAT_PCM_S16LE   = 2;
}

// Streaming messages (defined now, handler stubbed)
message AudioChunk {
  bytes audio = 1;
  AudioFormat format = 2;
  uint32 sample_rate = 3;
  bool is_final = 4;
  string request_id = 5;
}

message TranscribeEvent {
  oneof kind {
    InterimHypothesis interim = 1;
    FinalHypothesis  final   = 2;
  }
}

message InterimHypothesis {
  string text = 1;
  float confidence = 2;
}

message FinalHypothesis {
  string text = 1;
  repeated Word words = 2;
  float confidence = 3;
}
```

### 4.2 Error model

Errors are gRPC status codes, not in-band fields. Caller distinguishes recoverable vs fatal by code.

| Condition                                                | Status code          |
| -------------------------------------------------------- | -------------------- |
| Model not yet loaded                                     | `UNAVAILABLE`        |
| Empty audio bytes                                        | `INVALID_ARGUMENT`   |
| Unsupported `AudioFormat`                                | `INVALID_ARGUMENT`   |
| Sample rate outside `{8000, 16000, 22050, 44100, 48000}` | `INVALID_ARGUMENT`   |
| Audio longer than configured max                         | `RESOURCE_EXHAUSTED` |
| Decode failure (corrupt WAV, bad PCM)                    | `INVALID_ARGUMENT`   |
| Model inference exception                                | `INTERNAL`           |
| Streaming RPC called in v1                               | `UNIMPLEMENTED`      |
| Request cancelled by client                              | `CANCELLED`          |

Every error response carries a `request_id` in trailing metadata for log correlation.

### 4.3 Validation rules

The server validates in this order, short-circuiting on the first failure:

1. `format` is a known `AudioFormat`.
2. `audio` is non-empty.
3. `sample_rate` is in the allowed set.
4. Decoded audio duration is `<= STT_MAX_AUDIO_SECONDS` (default 120 seconds for v1; raise later if we need longer batches).
5. Decoded audio is mono. Stereo input gets downmixed to mono with a logged warning, not rejected.

---

## 5. Audio Pipeline

Input shapes the server accepts:

- **WAV** — parsed with `soundfile`. Any sample rate accepted; resampled to 16 kHz if needed.
- **PCM_S16LE** — raw little-endian 16-bit signed PCM. Caller must supply `sample_rate` and (implicitly) mono. We decode with `numpy.frombuffer(audio, dtype="<i2").astype("float32") / 32768.0`.

Internal canonical form: `numpy.float32` array, mono, 16 kHz, range `[-1.0, 1.0]`.

### Pipeline steps

```
bytes -> decode -> (optional) downmix to mono -> (optional) resample to 16kHz
       -> (optional) silero-vad trim -> Parakeet.transcribe()
       -> map to TranscribeResponse
```

**Resampling:** `librosa.resample` (under the hood it's `soxr` if available, which is fastest). Only invoked when input is not 16 kHz. Common case (`sample_rate == 16000`) skips it entirely.

**Downmix:** simple channel-mean. Stereo is the only realistic non-mono input from the Phase 2 Swift app; we don't try to be clever about multi-channel arrangements.

**VAD trim (opt-in):** when `trim_silence` is true on the request, we run silero-vad to find the first and last speech-active windows, then crop. This shaves model time on requests with long leading/trailing silence (common for push-to-talk). It does _not_ split utterances or endpoint anything — it's a pre-pass only.

### 5.1 Audio limits

| Limit                  | Default                                      | Env var                 |
| ---------------------- | -------------------------------------------- | ----------------------- |
| Max audio duration     | 120 s                                        | `STT_MAX_AUDIO_SECONDS` |
| Min audio duration     | 0.25 s                                       | `STT_MIN_AUDIO_SECONDS` |
| Max in-flight requests | 4 (queued via lock; lock has a wait timeout) | `STT_MAX_QUEUED`        |

Anything under `STT_MIN_AUDIO_SECONDS` returns an empty transcript with `confidence: 0.0` rather than erroring. This handles the Swift app's "user tapped the hotkey but said nothing" case gracefully.

---

## 6. Model Layer

`asr/model.py` wraps NeMo behind a tiny interface so the rest of the codebase doesn't import NeMo directly.

```python
class ParakeetModel:
    def __init__(self, model_name: str, device: str | None = None) -> None: ...

    async def load(self) -> None:
        """Load weights. Idempotent. Sets self.ready = True on success."""

    @property
    def ready(self) -> bool: ...

    async def transcribe(
        self,
        audio: np.ndarray,         # float32 mono @ 16kHz
        include_timestamps: bool,
    ) -> TranscriptionResult: ...

    async def warmup(self) -> None:
        """Run one no-op inference on a 1-second silence buffer so the first
        real request doesn't pay JIT/compile cost."""
```

### 6.1 Lifecycle

```
process start
   -> build server objects
   -> spawn ParakeetModel.load() as a background task
   -> /readyz returns 503 until model.ready is True
   -> /healthz always returns 200 once the process is up
   -> gRPC Transcribe returns UNAVAILABLE until model.ready
   -> after load, run warmup() once
   -> serve
```

Eager-loading at startup is deliberate. Lazy loading on first request creates a brutal first-request latency spike (~5-8 seconds) that breaks the Phase 2 UX where the user is staring at a "Transcribing…" notification.

### 6.2 Concurrency

A single `asyncio.Lock` guards `transcribe()`. Multiple concurrent gRPC calls serialize at the lock. This is intentional:

- NeMo's `transcribe()` is not safe to call concurrently on a single model instance.
- For CPU inference, real concurrency wouldn't help anyway — one process saturates available cores per call.
- For GPU inference, batching multiple calls would help, but adds complexity for a use case (one user, occasional voice commands) that doesn't need it.

If wait time at the lock exceeds `STT_QUEUE_WAIT_TIMEOUT_MS` (default 5000 ms), the request fails with `RESOURCE_EXHAUSTED`. Backpressure should be visible, not silent.

### 6.3 Device selection

```python
def pick_device() -> str:
    if os.environ.get("STT_DEVICE"):
        return os.environ["STT_DEVICE"]
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
```

CUDA preferred. MPS works for Apple Silicon dev runs but Parakeet on MPS has known precision quirks — fine for development, not recommended for production-quality transcription. CPU is the safe fallback and is fast enough for single-user voice commands on Apple Silicon.

### 6.4 Why not parakeet-mlx

On Apple Silicon, `parakeet-mlx` is faster than NeMo on CPU. We do not use it because:

- It locks the service to macOS — kills the "backend runs on Linux" property.
- It has a different output schema; we'd need a translation layer.
- The NeMo path is fast enough on the target hardware for v1 latency goals.

If MLX support becomes a hard requirement later, it would slot in as an alternate `ParakeetModel` implementation behind the same interface — not a rewrite.

---

## 7. Admin HTTP Surface

FastAPI, mounted at the gRPC server's sibling port (`STT_ADMIN_PORT`, default 8080).

| Route          | Behavior                                                                                                                |
| -------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `GET /healthz` | Returns `200 {"status":"ok"}` if the process is up. Never depends on model state.                                       |
| `GET /readyz`  | Returns `200 {"status":"ready","model":"<name>"}` if the model is loaded. Returns `503 {"status":"loading"}` otherwise. |
| `GET /info`    | Returns model name, device, max audio seconds, current queue depth. For ops, not for hot path use.                      |

No POST endpoints. No admin actions. Anything that mutates state goes through gRPC or process restart.

---

## 8. Configuration

Configuration is environment variables only. No YAML, no TOML. The service is small enough that env is cleaner than a config file, and it plays nicely with `docker-compose`, `systemd`, and `direnv` alike.

| Variable                    | Default                       | Purpose                                                              |
| --------------------------- | ----------------------------- | -------------------------------------------------------------------- |
| `STT_GRPC_HOST`             | `127.0.0.1`                   | Bind address for gRPC.                                               |
| `STT_GRPC_PORT`             | `50051`                       | Bind port for gRPC.                                                  |
| `STT_ADMIN_HOST`            | `127.0.0.1`                   | Bind address for FastAPI admin.                                      |
| `STT_ADMIN_PORT`            | `8080`                        | Bind port for FastAPI admin.                                         |
| `STT_MODEL_NAME`            | `nvidia/parakeet-tdt-0.6b-v2` | HF model id passed to NeMo.                                          |
| `STT_DEVICE`                | (auto)                        | Force device: `cuda`, `mps`, `cpu`.                                  |
| `STT_MAX_AUDIO_SECONDS`     | `120`                         | Reject longer audio.                                                 |
| `STT_MIN_AUDIO_SECONDS`     | `0.25`                        | Below this, return empty transcript.                                 |
| `STT_QUEUE_WAIT_TIMEOUT_MS` | `5000`                        | Max wait at the model lock before erroring.                          |
| `STT_VAD_DEFAULT`           | `false`                       | If true, default `trim_silence` to true when caller leaves it unset. |
| `STT_LOG_LEVEL`             | `INFO`                        | structlog level.                                                     |
| `HF_HOME`                   | `~/.cache/huggingface`        | Standard HF cache location; mount as a volume in containers.         |

A `pydantic-settings` `Settings` class in `config.py` is the single source of truth — everything reads `Settings()` rather than `os.environ`.

---

## 9. Logging & Observability

### Logging

`structlog` configured to emit JSON lines to stdout. Every log line carries:

- `timestamp` (ISO-8601, UTC)
- `level`
- `event` (the message)
- `request_id` (when in a request context)
- `service: "ore-stt"`

Per-request lifecycle logs:

```
{"event": "request.received", "request_id": "01JF...", "audio_bytes": 64012, "format": "WAV"}
{"event": "audio.decoded", "request_id": "01JF...", "duration_ms": 2843, "sample_rate": 16000}
{"event": "vad.trimmed", "request_id": "01JF...", "trimmed_ms": 410}
{"event": "inference.start", "request_id": "01JF...", "device": "cpu"}
{"event": "inference.done", "request_id": "01JF...", "inference_ms": 412}
{"event": "request.completed", "request_id": "01JF...", "latency_ms": 478, "chars": 87}
```

### Counters (for future Prometheus, surfaced via structured logs in v1)

- `stt_requests_total{status}`
- `stt_request_duration_ms` (histogram)
- `stt_inference_duration_ms` (histogram)
- `stt_audio_duration_ms` (histogram)
- `stt_queue_depth` (gauge)
- `stt_model_ready` (0/1 gauge)

v1 ships with logs only. A Prometheus exporter is a small addition once it's actually needed.

---

## 10. Performance Targets

| Metric                                               | Target on M-series CPU | Target on consumer GPU |
| ---------------------------------------------------- | ---------------------- | ---------------------- |
| Cold start (process up → model ready)                | < 8 s                  | < 10 s                 |
| Warm transcribe — 5 s clip                           | < 500 ms               | < 200 ms               |
| Warm transcribe — 30 s clip                          | < 2 s                  | < 600 ms               |
| Resident memory                                      | < 3 GB                 | < 4 GB (incl. VRAM)    |
| First-request latency after cold start (with warmup) | within 1.5x warm       | within 1.5x warm       |

These are budgets, not guarantees. Anything outside these on representative hardware is a perf bug, not a feature request.

---

## 11. Testing Strategy

Three layers, in order of cost and value:

**Unit tests (`tests/unit/`).** Pure functions: WAV decoding, PCM decoding, resampling correctness, VAD trim boundaries, config parsing, error mapping. No model loaded. Run on every commit. Target: < 5 seconds total.

**Integration tests (`tests/integration/`).** Spin up the gRPC handler with a stub `ParakeetModel` (returns canned `TranscriptionResult` objects). Verify the full request lifecycle: validation, decode, lock acquisition, response shape, error codes. Tests the wiring, not the model. Run on every commit. Target: < 15 seconds total.

**End-to-end smoke (manual + occasional CI on a GPU runner).** A pytest marker `@pytest.mark.e2e` loads the real model and transcribes fixture WAV files. Asserts WER against expected transcripts within a tolerance. Run manually before releases or nightly on a self-hosted GPU runner. Never on every commit — model download alone defeats CI economics.

### Fixtures

`tests/fixtures/` ships:

- `hello.wav` — 1.5 s, "hello world"
- `long.wav` — 25 s, longer paragraph for benchmarking
- `silence.wav` — 2 s, pure silence (VAD test)
- `noisy.wav` — 4 s, low-SNR speech (robustness sanity check)

All are short, royalty-free, and committed to the repo. No remote downloads in CI.

---

## 12. Build & Run

### Local dev

```bash
# one-time
uv sync                                  # installs from uv.lock
make proto                               # generate gRPC stubs

# run
uv run python -m ore_stt                 # starts gRPC + FastAPI
```

`uv run` activates the virtualenv implicitly; no `source .venv/bin/activate` needed.

### Common make targets

```makefile
.PHONY: dev lint format typecheck test proto run docker

dev:        ## install dev deps
 uv sync --all-extras

lint:       ## ruff check
 uv run ruff check src tests

format:     ## ruff format
 uv run ruff format src tests

typecheck:  ## mypy strict
 uv run mypy src

test:       ## fast tests only (no e2e)
 uv run pytest -m "not e2e" tests/

test-e2e:   ## full tests including real model
 uv run pytest tests/

proto:      ## regenerate gRPC stubs
 uv run python -m grpc_tools.protoc \
  -I proto \
  --python_out=src/ore_stt/grpc/generated \
  --pyi_out=src/ore_stt/grpc/generated \
  --grpc_python_out=src/ore_stt/grpc/generated \
  proto/ore/stt/v1/stt.proto

run:        ## run server
 uv run python -m ore_stt

docker:     ## build container image
 docker build -t ore-stt:dev .
```

### Container

```dockerfile
FROM python:3.11-slim AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Layer 1: deps (changes rarely)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Layer 2: source (changes often)
COPY src/ ./src/
COPY proto/ ./proto/

# Generate stubs at build time
RUN uv run python -m grpc_tools.protoc \
        -I proto \
        --python_out=src/ore_stt/grpc/generated \
        --pyi_out=src/ore_stt/grpc/generated \
        --grpc_python_out=src/ore_stt/grpc/generated \
        proto/ore/stt/v1/stt.proto

EXPOSE 50051 8080
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s \
    CMD curl -fsS http://localhost:8080/healthz || exit 1

CMD ["uv", "run", "python", "-m", "ore_stt"]
```

Model weights are NOT baked into the image. The container mounts `HF_HOME` as a volume and downloads on first run. Keeps the image small and lets the user update the model independently.

---

## 13. Tooling Configurations

### `pyproject.toml` (sketch)

```toml
[project]
name = "ore-stt"
version = "0.1.0"
description = "Speech-to-text service for the Ore agent."
requires-python = ">=3.11,<3.12"
dependencies = [
    "grpcio>=1.62",
    "grpcio-tools>=1.62",
    "protobuf>=5.0",
    "nemo-toolkit[asr]>=2.0",
    "torch>=2.2",
    "soundfile>=0.12",
    "librosa>=0.10",
    "numpy>=1.26,<2.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "structlog>=24.1",
    "silero-vad>=5.0",
    "python-ulid>=2.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "grpcio-testing>=1.62",
    "ruff>=0.4",
    "mypy>=1.10",
    "types-protobuf",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### `.ruff.toml`

```toml
target-version = "py311"
line-length = 100

[lint]
select = [
    "E",   # pycodestyle
    "F",   # pyflakes
    "I",   # isort
    "B",   # bugbear
    "UP",  # pyupgrade
    "SIM", # simplify
    "RUF", # ruff-specific
]
ignore = ["E501"]  # line length handled by formatter

[lint.per-file-ignores]
"src/ore_stt/grpc/generated/**" = ["ALL"]  # generated code is not ours to lint
"tests/**" = ["B018"]                       # tests can use otherwise-meaningless expressions

[format]
quote-style = "double"
```

### `mypy.ini`

```ini
[mypy]
python_version = 3.11
strict = True
warn_unreachable = True
disallow_untyped_decorators = True
ignore_missing_imports = False

[mypy-nemo.*]
ignore_missing_imports = True

[mypy-librosa.*]
ignore_missing_imports = True

[mypy-soundfile.*]
ignore_missing_imports = True

[mypy-silero_vad.*]
ignore_missing_imports = True

[mypy-ore_stt.grpc.generated.*]
ignore_errors = True
```

---

## 14. Security Posture

`ore-stt` is a localhost-only service in v1. The following hold:

- Binds to `127.0.0.1` by default. Override via `STT_GRPC_HOST` only for trusted networks (Tailscale, container network).
- No authentication. The agent is the sole intended client, on the same host or network namespace.
- No persistence. Audio is decoded into memory and discarded after transcription. No transcripts are stored by this service — that's the agent's job.
- No outbound network traffic except the one-time model download from Hugging Face on first run. The container should declare this explicitly.
- gRPC max message size is bumped to 16 MB (default 4 MB is too small for a 2-minute WAV).
- The admin HTTP surface returns no PII, no model internals — just liveness, readiness, and aggregate config.

If multi-host deployment becomes a thing, mTLS goes between agent and STT. That decision is deferred until the topology demands it.

---

## 15. Open Questions

1. **Streaming RPC delivery.** The `.proto` defines `TranscribeStream` but the v1 implementation returns `UNIMPLEMENTED`. When does it land? Suggest: Phase 1.5, only if the Swift app's UX benefits materially from interim hypotheses.
2. **Multi-channel audio policy.** Currently we downmix stereo to mono with a warning. Should we reject instead? Suggest: keep downmix, the desktop is the most likely source and might send stereo by default.
3. **MLX path for Apple Silicon.** If/when latency on M-series CPU becomes the bottleneck, do we add `parakeet-mlx` as an alternate model backend, or punt to GPU hosting? Suggest: revisit when measured latency exceeds budget.
4. **Telemetry transport.** Logs in v1, Prometheus later. When? Suggest: when we have a second deployment (i.e., the Hetzner box) where we actually care about cross-host metrics.
5. **Audio retention for debugging.** Right now audio is discarded immediately. For diagnosing transcription failures, a temporary on-disk capture (last N failed requests) might help. Suggest: opt-in env flag, off by default, with auto-prune.

---

## 16. Milestones (ore-stt only)

| #   | Scope               | Done when                                                                                              |
| --- | ------------------- | ------------------------------------------------------------------------------------------------------ |
| S1  | Skeleton            | Repo builds, `uv sync` works, lint and typecheck pass, `python -m ore_stt` starts a no-op gRPC server. |
| S2  | Admin surface       | `/healthz` and `/readyz` work. `/readyz` returns 503 until a dummy "model loaded" flag is set.         |
| S3  | Audio decoding      | WAV and PCM decoders + tests. No model yet.                                                            |
| S4  | Real model          | Parakeet loads at startup, warmup runs, `Transcribe` RPC returns real transcripts for fixture WAVs.    |
| S5  | Validation + errors | All gRPC error codes from §4.2 covered by integration tests.                                           |
| S6  | VAD pre-pass        | `trim_silence` opt-in works, silence fixture handled correctly.                                        |
| S7  | Container           | Image builds, healthcheck passes, model loads from mounted HF cache.                                   |
| S8  | E2E sanity          | WER-against-expected test for `hello.wav` and `long.wav` passes on a GPU runner.                       |

after S8, ore-stt is ready for the Go agent (`ore`) to consume.

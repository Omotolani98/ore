FROM python:3.11-slim AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
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

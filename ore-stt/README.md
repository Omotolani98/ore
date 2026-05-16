# ore-stt

Speech-to-text service for the Ore agent system. A long-running daemon that loads NVIDIA
Parakeet TDT 0.6B v2 once at startup and transcribes audio over gRPC. Single responsibility:
**audio bytes → transcript**.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full design.

## Development

Requires [`uv`](https://docs.astral.sh/uv/). Python 3.11 is auto-installed by `uv`.

```bash
uv sync --all-extras          # install deps (make dev)
make proto                    # generate gRPC stubs
uv run python -m ore_stt      # run the server (make run)
```

| Target           | Action                                  |
| ---------------- | --------------------------------------- |
| `make dev`       | install dev deps                        |
| `make proto`     | regenerate gRPC stubs from `proto/`      |
| `make lint`      | `ruff check`                            |
| `make format`    | `ruff format`                           |
| `make typecheck` | `mypy --strict`                         |
| `make test`      | fast tests (unit + integration, no e2e) |
| `make test-e2e`  | full tests including the real model     |
| `make run`       | start the server                        |
| `make docker`    | build the container image               |

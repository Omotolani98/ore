.PHONY: dev lint format typecheck test test-e2e proto run docker help

help:       ## list targets
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

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

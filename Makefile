.PHONY: sync lint fmt typecheck test test-docker check pull-images

sync:
	uv sync

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

typecheck:
	uv run mypy

test:
	uv run pytest -m "not docker"

test-docker:
	uv run pytest -m docker

check: lint typecheck test

pull-images:
	uv run python scripts/pull_images.py

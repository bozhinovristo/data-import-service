.PHONY: help install fetch seed run ui test cov lint format format-check typecheck gate docker-build docker-run clean

help:
	@echo "Targets:"
	@echo "  install       Install dependencies via Poetry"
	@echo "  fetch         Fetch employees from the API and store them"
	@echo "  seed          Seed demo data and export employees.json / .csv"
	@echo "  run           Run the FastAPI service on :8000"
	@echo "  ui            Serve the demo UI on :5500 (needs mock server on :8001)"
	@echo "  test          Run the test suite"
	@echo "  cov           Run tests with a coverage report"
	@echo "  lint          Lint with ruff"
	@echo "  format        Format with black"
	@echo "  typecheck     Type-check with mypy"
	@echo "  gate          Run lint + format-check + typecheck + test"
	@echo "  docker-build  Build the Docker image"
	@echo "  docker-run    Run the service in Docker (needs .env)"

install:
	poetry install

fetch:
	poetry run python -m src.fetch_cmd

seed:
	poetry run python -m src.seed_cmd

run:
	poetry run uvicorn src.service:app --reload --port 8000

ui:
	python -m http.server 5500 --directory frontend

test:
	poetry run pytest

cov:
	poetry run pytest --cov=src --cov-report=term-missing

lint:
	poetry run ruff check .

format:
	poetry run black .

format-check:
	poetry run black --check .

typecheck:
	poetry run mypy src/

gate: lint format-check typecheck test

docker-build:
	docker build -t data-import-service .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env data-import-service

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov

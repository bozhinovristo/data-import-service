# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# Install Poetry, then dependencies (this layer is cached unless the lock changes).
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi --no-root --without dev

# Copy the application source.
COPY src ./src
COPY README.md ./

EXPOSE 8000

# Serve the read-only API. Required env vars must be supplied at run time, e.g.:
#   docker run --rm -p 8000:8000 --env-file .env data-import-service
CMD ["uvicorn", "src.service:app", "--host", "0.0.0.0", "--port", "8000"]

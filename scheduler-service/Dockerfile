FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip && pip install poetry

COPY pyproject.toml poetry.lock README.md ./
COPY src ./src
COPY migrations ./migrations

RUN poetry install --only main

EXPOSE 8087

CMD ["uvicorn", "scheduler_service.main:app", "--host", "0.0.0.0", "--port", "8087"]


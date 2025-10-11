FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && pip install poetry

COPY pyproject.toml poetry.lock README.md ./
COPY src ./src

RUN poetry install --no-root --only main

EXPOSE 8088

CMD ["poetry", "run", "uvicorn", "scheduler_mcp.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8088"]

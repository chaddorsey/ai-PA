FROM python:3.11-slim

WORKDIR /app

# Install poetry
RUN pip install poetry==1.8.4

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev deps, no virtualenv in container)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main

# Copy source code
COPY src/ ./src/

# Expose port
EXPOSE 5201

# Run the application
CMD ["uvicorn", "pa_routing.main:app", "--host", "0.0.0.0", "--port", "5201"]

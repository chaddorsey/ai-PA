FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    gnupg \
    jq \
    git \
    bash \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/* \
    && echo '#!/bin/bash\nexec docker compose "$@"' > /usr/local/bin/docker-compose \
    && chmod +x /usr/local/bin/docker-compose

RUN pip install --upgrade pip && pip install poetry

# Install gws CLI (Google Workspace) so cron-driven scripts can issue
# direct Calendar/Gmail/Drive/Admin Reports API calls via Bash. Mirrors
# the letta and pa-web-ui patterns. Credentials are mounted at
# /root/.gws/credentials.json by docker-compose.
COPY scripts/update-gws.sh /tmp/update-gws.sh
RUN bash /tmp/update-gws.sh \
    && rm /tmp/update-gws.sh \
    && gws --version

COPY pyproject.toml poetry.lock README.md ./
COPY src ./src
COPY migrations ./migrations

RUN poetry install --only main

EXPOSE 8087

CMD ["uvicorn", "scheduler_service.main:app", "--host", "0.0.0.0", "--port", "8087"]

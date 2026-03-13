FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install twitter-cli first (changes less frequently)
COPY twitter-cli/ ./twitter-cli/
RUN pip install --no-cache-dir ./twitter-cli

# Install curator-radar dependencies
COPY curator-radar/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY curator-radar/curator_radar/ ./curator_radar/

EXPOSE 5145

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5145/health || exit 1

CMD ["uvicorn", "curator_radar.main:app", "--host", "0.0.0.0", "--port", "5145"]

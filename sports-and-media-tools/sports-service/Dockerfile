FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY sports_api.py .

# Create data directory for cache
RUN mkdir -p /app/data

EXPOSE 5123

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5123/health || exit 1

CMD ["python", "sports_api.py"]


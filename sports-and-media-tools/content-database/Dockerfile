FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create data directory for SQLite
RUN mkdir -p /app/data

# Copy application files
COPY justwatch_scraper.py .
COPY content_api.py .

# Environment variables
ENV CONTENT_DB_PATH=/app/data/content_database.db
ENV PYTHONUNBUFFERED=1

EXPOSE 5126

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5126", "--workers", "2", "--timeout", "120", "content_api:app"]


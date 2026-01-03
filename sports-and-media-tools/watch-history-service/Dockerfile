# Use official Playwright image which has browsers pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py .

# Create directories
RUN mkdir -p /app/data /app/credentials

# Environment variables
ENV DB_PATH=/app/data/content_database.db
ENV CREDENTIALS_PATH=/app/credentials

EXPOSE 5127

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5127", "--workers", "2", "--timeout", "120", "watch_history_poller:app"]

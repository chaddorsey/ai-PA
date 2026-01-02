FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY schedules_api.py .

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 5125

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5125", "--workers", "2", "--timeout", "120", "schedules_api:app"]


FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.115.* \
    'uvicorn[standard]==0.30.*' \
    httpx==0.27.* \
    jinja2==3.1.* \
    websockets==13.*

COPY app/ /app/
COPY templates/ /app/templates/
COPY static/ /app/static/

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--access-log", "--log-level", "info"]

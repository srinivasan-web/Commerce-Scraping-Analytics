FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
RUN python -m playwright install --with-deps chromium
COPY backend /app/backend

EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

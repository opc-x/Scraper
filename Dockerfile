FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

ENV CHROMIUM_PATH=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir . && echo "[build] pip install OK"

EXPOSE 80

CMD ["sh", "-c", "echo '[boot] starting...' && python -c 'from app.main import app; print(\"[boot] import OK\")' && exec python -u -m uvicorn app.main:app --host 0.0.0.0 --port 80"]

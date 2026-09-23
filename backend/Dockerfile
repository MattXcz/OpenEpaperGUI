FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIR=/app/frontend \
    DATA_DIR=/data

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY frontend ./frontend

# Fonts for the pixel-accurate preview are fetched at build time rather than
# committed, so the repository stays free of ~4.5 MB of binaries. Each file is
# verified against its expected size and git blob SHA-1; a mismatch fails the
# build instead of shipping a wrong font.
RUN python scripts/fetch_assets.py

RUN mkdir -p /data

EXPOSE 8000

# Shell form wrapper so LOG_LEVEL is honoured; `exec` keeps uvicorn as PID 1
# so it still receives SIGTERM from `docker compose down`.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level \"${LOG_LEVEL:-info}\""]
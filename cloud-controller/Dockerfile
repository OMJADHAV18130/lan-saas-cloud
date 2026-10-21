# ---------------------------------------------------------------------------
# Cloud Controller image.
#
# Build context is the REPOSITORY ROOT (see docker-compose.yml) so that both
# the backend and the built frontend can be copied in.
# ---------------------------------------------------------------------------

# ---------- stage 1: build the React SPA ----------
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty base URL => the SPA calls the same origin (/api/...), which is correct
# when the controller serves the built files.
ENV VITE_API_BASE_URL=""
RUN npm run build


# ---------- stage 2: python runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl is used by the container healthcheck; everything else is pure Python.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY cloud-controller/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY cloud-controller/app ./app
COPY cloud-controller/pytest.ini ./pytest.ini

# Built SPA served by FastAPI (single-origin deployment, no CORS needed).
COPY --from=frontend-build /build/dist ./static

# SQLite lives on a volume so metadata survives container replacement.
RUN mkdir -p /data \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app /data
VOLUME ["/data"]
USER appuser

ENV STATIC_DIR=/app/static \
    DATABASE_URL=sqlite:////data/lan_saas.db \
    HDFS_ADAPTER=webhdfs \
    HDFS_BASE_URL=http://namenode:9870 \
    HDFS_SERVICE_USER=saascloud \
    HDFS_ROOT=/saas-cloud \
    ENVIRONMENT=production

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# One worker by default: SQLite + the in-process rate limiter are per-process.
# Override with the UVICORN_WORKERS variable only after moving to PostgreSQL.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1} --proxy-headers"]

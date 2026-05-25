# EnterpriseCore AI Suite — backend container
# Multi-stage build: deps installed in a builder image and copied as a
# non-root user-local install into the runtime image.

# ---------------------------------------------------------------------------
# Stage 1: builder
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build tools needed for psycopg2-binary fallback paths, cryptography wheels
# on some arches, and any C-extension wheels not available for slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --user -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

# Minimal runtime deps: wget for healthcheck, libpq5 for psycopg2 client lib.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget \
        libpq5 \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r enterprisecore \
    && useradd -r -g enterprisecore -d /app -s /sbin/nologin enterprisecore \
    && mkdir -p /data /app \
    && chown -R enterprisecore:enterprisecore /app /data

WORKDIR /app

# Copy site-packages from builder (installed under /root/.local; relocate to
# the runtime user's home so the user owns its own packages).
COPY --from=builder /root/.local /home/enterprisecore/.local
RUN chown -R enterprisecore:enterprisecore /home/enterprisecore

# Application code
COPY --chown=enterprisecore:enterprisecore backend/ ./backend/

USER enterprisecore

ENV PATH=/home/enterprisecore/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_FORMAT=json \
    ENTERPRISECORE_DATA_DIR=/data \
    APP_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8765 \
    BACKEND_PORT=8765

EXPOSE 8765

# Persistent data: SQLite file (if DB_BACKEND=sqlite), uploads, knowledge
# index, logs. Bind to a host directory or a named volume in compose/k8s.
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8765/api/health || exit 1

WORKDIR /app/backend

# tini = PID 1, reaps zombies and forwards signals cleanly to uvicorn workers.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "2"]

# EnterpriseCore AI Suite — frontend container
# Builds the Vite SPA and serves it via nginx with backend pass-through.

# ---------------------------------------------------------------------------
# Stage 1: build the SPA
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

# Copy lockfile first for cache friendliness
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: nginx
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

# Drop default config; ours lives in /etc/nginx/conf.d/default.conf.
RUN rm -f /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
COPY deploy/nginx/nginx.conf /etc/nginx/conf.d/default.conf

# The default nginx image already runs as root for port 80, but the worker
# processes run as nginx. For non-root operation, use an unprivileged base
# image (nginxinc/nginx-unprivileged) — see deploy/k8s for that variant.

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/healthz || exit 1

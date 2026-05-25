# Docker assets

The primary container build files live at the repo root so they can be the
default context for `docker build` and CI:

- `Dockerfile` — backend (multi-stage, non-root, healthcheck)
- `nginx.Dockerfile` — frontend (Vite build + nginx serve)
- `docker-compose.yml` — local dev / small self-host
- `docker-compose.override.yml.example` — dev overrides
- `.dockerignore` — build context filter

Supporting config:

- `../nginx/nginx.conf` — nginx config baked into the frontend image

This directory is reserved for ancillary Docker assets (extra Dockerfiles for
CI runners, debug images, etc.). It's intentionally empty today.

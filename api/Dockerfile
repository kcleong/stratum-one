# Build context: repo root (see compose.yml).

# --- web UI (Vue + ECharts) ---
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- API ---
FROM ghcr.io/astral-sh/uv:python3.14-alpine
# chronyc talks to chronyd over the shared /run/chrony socket.
RUN apk add --no-cache chrony
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/app/.venv/bin:$PATH
WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY api/pyproject.toml api/uv.lock api/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
COPY api/stratum_api ./stratum_api
COPY --from=web /web/dist ./static
CMD ["python", "-m", "stratum_api"]

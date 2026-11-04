# One image for the game: the frontend is built in a first stage, the Python app runs in
# the second and serves both the API and the built frontend.

# --- Stage 1: build the frontend (only its output, dist/, is kept) ---
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: the Python app ---
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first: this layer is reused as long as they do not change.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev

COPY game ./game
COPY --from=frontend /frontend/dist ./frontend/dist

# The pool is mounted at /app/pool and the database folder at /data (docker-compose.yml).
ENV PATH="/app/.venv/bin:$PATH" \
    DATABASE=/data/game.db \
    POOL_DIR=/app/pool \
    FRONTEND_DIR=/app/frontend/dist

# Not root. On the server data/ belongs to this user (uid 999).
RUN useradd --system --no-create-home app
USER app

EXPOSE 8000
CMD ["uvicorn", "game.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY prompts ./prompts
COPY app ./app
COPY importer ./importer
COPY scripts ./scripts

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --system --no-create-home app
USER app

EXPOSE 8000
# Apply pending database migrations, then start the API.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]

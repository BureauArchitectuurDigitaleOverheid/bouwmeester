FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen


FROM python:3.13-slim

RUN useradd --create-home --uid 1001 appuser

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app /app

USER 1001

# Activate venv via PATH — entrypoint uses python/alembic/uvicorn directly
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

ENTRYPOINT ["sh", "/app/entrypoint.sh"]

FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen


FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1001 appuser && \
    mkdir -p /data/bijlagen/chat /data/bijlagen/leads && \
    chgrp -R 0 /data && \
    chmod -R g=u /data

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app /app
# age-recipients.txt is copied into the build context by CI; wildcard
# makes it optional for local builds where encryption is not needed.
COPY --chown=appuser:appuser age-recipients.tx[t] /app/

USER 1001

# Activate venv via PATH — entrypoint uses python/alembic/uvicorn directly
ENV PATH="/app/.venv/bin:$PATH"

# Force unbuffered stdout/stderr — without this Python buffers when stdout
# is not a TTY, so the worker's log lines (and crash tracebacks) sit in the
# buffer until the process exits, making operational issues invisible.
ENV PYTHONUNBUFFERED=1

ARG GIT_SHA=""
ARG BUILD_TIME=""
ENV GIT_SHA=$GIT_SHA
ENV BUILD_TIME=$BUILD_TIME

EXPOSE 8080

ENTRYPOINT ["sh", "/app/entrypoint.sh"]

# =============================================================================
# Production multi-stage build: frontend (nginx) + backend (uvicorn)
# =============================================================================

# Stage 1: Build the frontend
FROM node:22-slim AS frontend-builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ .
COPY docs/ /docs/
RUN npm run build


# Stage 2: Build the backend
FROM python:3.13-slim AS backend-builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --frozen --no-install-project

COPY backend/ .
RUN uv sync --frozen


# Stage 3: Production runtime
FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx supervisor postgresql-client && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy backend
WORKDIR /app
COPY --from=backend-builder /app /app
COPY age-recipients.txt /app/age-recipients.txt

# Copy frontend build to nginx
COPY --from=frontend-builder /app/dist /usr/share/nginx/html

# Nginx configuration
RUN rm /etc/nginx/sites-enabled/default
COPY <<'NGINX_CONF' /etc/nginx/conf.d/bouwmeester.conf
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # API proxy to backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX_CONF

# Supervisor configuration to run both nginx and uvicorn
COPY <<'SUPERVISOR_CONF' /etc/supervisor/conf.d/bouwmeester.conf
[supervisord]
nodaemon=true
logfile=/dev/null
logfile_maxbytes=0

[program:nginx]
command=nginx -g "daemon off;"
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:backend]
command=uv run uvicorn bouwmeester.core.app:create_app --factory --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='*'
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:worker]
command=uv run python -m bouwmeester.worker
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
SUPERVISOR_CONF

EXPOSE 80

CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]

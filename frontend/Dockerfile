FROM node:22-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
# Copy docs for the in-app documentation page (CI places docs/ in the context)
COPY doc[s] /docs/
RUN npm run build


FROM node:22-slim AS dev

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]


FROM nginxinc/nginx-unprivileged:alpine AS production

COPY --from=builder /app/dist /usr/share/nginx/html

# Replace main nginx.conf to avoid port 80 and user directive issues
COPY <<'NGINX' /etc/nginx/nginx.conf
worker_processes auto;
error_log /var/log/nginx/error.log notice;
pid /tmp/nginx.pid;

events {
    worker_connections 1024;
}

http {
    client_body_temp_path /tmp/client_temp;
    proxy_temp_path /tmp/proxy_temp;
    fastcgi_temp_path /tmp/fastcgi_temp;
    uwsgi_temp_path /tmp/uwsgi_temp;
    scgi_temp_path /tmp/scgi_temp;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    keepalive_timeout 65;

    server {
        listen 8080;
        server_name _;

        root /usr/share/nginx/html;
        index index.html;

        # Prevent nginx from including the internal port in redirects
        # (we run behind a reverse proxy on a different port)
        absolute_redirect off;

        # Hashed assets — immutable, cache forever
        location /assets/ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }

        # Frontend SPA fallback — never cache index.html so deploys take effect
        location / {
            try_files $uri /index.html;
            add_header Cache-Control "no-cache";
        }
    }
}
NGINX

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]

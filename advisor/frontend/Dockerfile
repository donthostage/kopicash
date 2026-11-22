FROM nginxinc/nginx-unprivileged:1.28-alpine
ARG ADVISOR_REVISION
COPY frontend/default.conf /etc/nginx/conf.d/default.conf
COPY wallet.html welcome.html wallet-cashback.js pocket.webp /usr/share/nginx/html/
COPY static/ /usr/share/nginx/html/static/
USER root
RUN printf '%s\n' "$ADVISOR_REVISION" | grep -xE '[0-9a-f]{40}' > /usr/share/nginx/html/frontend-revision
USER 101
EXPOSE 8080

FROM node:24-alpine AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src/ ./src/
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine
ARG ADVISOR_REVISION
COPY frontend/default.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/dist/ /usr/share/nginx/html/
COPY pocket.webp /usr/share/nginx/html/
COPY static/ /usr/share/nginx/html/static/
USER root
RUN printf '%s\n' "$ADVISOR_REVISION" | grep -xE '[0-9a-f]{40}' > /usr/share/nginx/html/frontend-revision
USER 101
EXPOSE 8080

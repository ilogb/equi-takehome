# Build context is the repo root (compose and CapRover both use it).
FROM node:22-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

FROM nginx:1.27-alpine
# nginx renders /etc/nginx/templates/*.template with envsubst at start-up.
ENV API_UPSTREAM=api:8000
COPY web/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

# InterCiter web UI — build the Vite SPA, serve it with nginx.
#
# nginx also reverse-proxies /v1 and /health to the API service so the browser
# sees a single origin (docs/ui-design.md §3) — the BFF session cookie (§11)
# works without CORS.

# --- Build stage ------------------------------------------------------------
FROM node:22-slim AS build

WORKDIR /app

# Install dependencies against the lockfile-adjacent manifest first for caching.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# --- Runtime stage ----------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# API upstream is templated so it can be overridden at container start.
ENV API_UPSTREAM=http://backend:8000

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

# nginx:alpine's entrypoint renders /etc/nginx/templates/*.template with envsubst
# (substituting $API_UPSTREAM) into /etc/nginx/conf.d before starting.

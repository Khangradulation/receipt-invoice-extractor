# syntax=docker/dockerfile:1
# Production image: static Vite build served by unprivileged nginx on port 8080 (Cloud Run).
# VITE_* values are compiled into the bundle at build time and are public by nature —
# never pass secrets here.

FROM node:25-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE_URL=""
ARG VITE_FIREBASE_API_KEY=""
ARG VITE_FIREBASE_AUTH_DOMAIN=""
ARG VITE_FIREBASE_PROJECT_ID=""
ARG VITE_FIREBASE_APP_ID=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY \
    VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN \
    VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID \
    VITE_FIREBASE_APP_ID=$VITE_FIREBASE_APP_ID
RUN npm run build
# Put the API's origin (scheme://host[:port]) into the CSP's connect-src.
RUN api_origin="$(printf '%s' "$VITE_API_BASE_URL" | sed -E 's#^(https?://[^/]+).*#\1#')" && \
    case "$api_origin" in ""|http://*|https://*) ;; *) echo "bad VITE_API_BASE_URL" >&2; exit 1 ;; esac && \
    sed "s#__API_ORIGIN__#${api_origin}#" security-headers.conf > /tmp/security-headers.conf

FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime
COPY --from=build /tmp/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080

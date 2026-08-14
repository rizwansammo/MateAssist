# One Dockerfile for both SPAs, selected by build arg.
#
#     docker build -f frontend/Dockerfile --build-arg APP=portal frontend/
#     docker build -f frontend/Dockerfile --build-arg APP=admin  frontend/
#
# Build context is ./frontend, which is the npm workspace root (D-104): both
# apps import the shared @mateassist/ui package from ./packages, so neither can
# be built from its own directory alone.
#
# The API is NOT baked in. Both apps call the relative path /api/v1, which the
# edge nginx proxies to Django on the same host - so one image serves every
# tenant subdomain and the apex, and changing the domain needs no rebuild. That
# is the whole reason the client uses a relative base URL rather than an
# absolute one supplied at build time.

# ---------------------------------------------------------------- builder ----
FROM node:22-alpine AS builder

ARG APP
RUN test -n "$APP" || (echo "APP build arg is required (portal|admin)" && exit 1)

WORKDIR /repo

# Manifests before sources, so editing a component reuses the install layer.
COPY package.json package-lock.json ./
COPY portal/package.json ./portal/
COPY admin/package.json ./admin/
COPY packages/ui/package.json ./packages/ui/

RUN npm ci

COPY . .

# The build runs in production mode, which is what switches the admin bundle to
# base=/platform_admin/ (D-147). Built in any other mode its asset URLs point at
# the apex root and 404 behind the path prefix - a blank page with a clean
# console.
RUN npm run build --workspace "$APP"

# ---------------------------------------------------------------- runtime ----
FROM nginx:1.27-alpine AS runtime

ARG APP

COPY --from=builder /repo/${APP}/dist /usr/share/nginx/html
COPY docker/spa.conf /etc/nginx/conf.d/default.conf

# Both SPAs listen on 8080 inside the container; the host nginx maps each to a
# different loopback port.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1

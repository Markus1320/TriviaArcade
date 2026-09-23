# Build the static frontend, then serve it with Caddy.
# Caddy is the single entry point: it serves these files and proxies /api to the backend.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv

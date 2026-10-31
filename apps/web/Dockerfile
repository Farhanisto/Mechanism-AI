FROM node:20-alpine AS build

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web ./
RUN npm run build

FROM nginx:1.27-alpine

ENV PORT=80 \
    API_UPSTREAM=api:8000 \
    NGINX_ENVSUBST_FILTER='PORT|API_UPSTREAM|DNS_RESOLVER'

COPY apps/web/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY apps/web/conf.d/10-rate-limit.conf /etc/nginx/conf.d/10-rate-limit.conf
COPY apps/web/docker-entrypoint.d/15-railway-dns.envsh /docker-entrypoint.d/15-railway-dns.envsh
RUN chmod +x /docker-entrypoint.d/15-railway-dns.envsh

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80 8080

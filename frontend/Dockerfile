FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE=/api/v1
ARG VITE_PUBLIC_BASE=/
ARG VITE_DEV_PORT=5173
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_PUBLIC_BASE=${VITE_PUBLIC_BASE}
ENV VITE_DEV_PORT=${VITE_DEV_PORT}

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/nginx.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

ENV BASE_PATH=""

RUN printf '#!/bin/sh\nenvsubst "\$BASE_PATH" < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf\nexec nginx -g "daemon off;"\n' > /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

CMD ["/docker-entrypoint.sh"]

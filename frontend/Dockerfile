FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE=/api/v1
ARG VITE_DEV_PORT=5173
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_DEV_PORT=${VITE_DEV_PORT}

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

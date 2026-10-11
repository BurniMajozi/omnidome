ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY apps/web/components /app/components
COPY apps/web/lib /app/lib
COPY apps/web/app /app/app
COPY apps/web/proxy.ts /app/proxy.ts
RUN npm run build

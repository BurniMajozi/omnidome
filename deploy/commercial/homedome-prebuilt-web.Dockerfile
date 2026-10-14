ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY web-next /app/.next
COPY package.json /app/package.json

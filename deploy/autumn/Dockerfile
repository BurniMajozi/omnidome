# Upstream 89b5b6dc runtime, adapted for hosts using Docker's legacy builder.
FROM oven/bun:1.4.2
WORKDIR /app
COPY . .
RUN bun install --ignore-scripts --frozen-lockfile
ENV NODE_ENV=production
WORKDIR /app/server
EXPOSE 8080
CMD ["bun", "start"]

FROM node:20-slim AS builder

WORKDIR /app

COPY apps/customer-portal/package.json apps/customer-portal/package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY apps/customer-portal/ ./

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_DISABLE_TURBOPACK=1

RUN npm run build

FROM node:20-slim

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_DISABLE_TURBOPACK=1
ENV PORT=3001

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3001/', (r) => { process.exit(r.statusCode === 200 ? 0 : 1) })"

CMD ["npm", "run", "start"]

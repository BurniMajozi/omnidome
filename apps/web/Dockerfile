FROM node:20-alpine

WORKDIR /app

# Corporate proxy TLS interception workaround
ENV NODE_TLS_REJECT_UNAUTHORIZED=0

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm config set strict-ssl false && npm ci --legacy-peer-deps

COPY apps/web/ ./

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]

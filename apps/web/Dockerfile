FROM node:20-slim

WORKDIR /app

# Corporate proxy TLS interception workaround
ENV NODE_TLS_REJECT_UNAUTHORIZED=0

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm config set strict-ssl false && npm ci --legacy-peer-deps

COPY apps/web/ ./

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_DISABLE_TURBOPACK=1

# NEXT_PUBLIC_* are inlined by `next build`, so they must exist at BUILD time.
# Railway passes every service variable as a --build-arg for Dockerfile builds;
# declare them here (ARG) and promote to ENV so `next build` can read them.
# Without this, lib/supabase/client fail-fasts at import and prerendering
# /auth/callback aborts the build.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_GATEWAY_URL
ARG NEXT_PUBLIC_SIM_URL
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_GATEWAY_URL=$NEXT_PUBLIC_GATEWAY_URL \
    NEXT_PUBLIC_SIM_URL=$NEXT_PUBLIC_SIM_URL

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]

/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  experimental: {
    turbopackUseSystemTlsCerts: true,
  },
  async rewrites() {
    return [
      // Gateway (primary API proxy)
      { source: '/gateway/:path*', destination: 'http://localhost:8000/:path*' },
      // Individual microservice proxies
      // NOTE: /svc/crm, /svc/billing, /svc/inventory, /svc/compliance, /svc/memory,
      // /svc/marketing, and /svc/finance are each handled by their own App Router
      // route handler under app/svc/<service>/[...path]/route.ts, which reads the
      // service's *_SERVICE_URL env var (the Docker Compose hostname). Those rewrite
      // entries are intentionally absent here — empirically, this rewrites() array
      // wins over the route handlers for the same path (despite Next.js docs saying
      // filesystem routes take priority over default/afterFiles rewrites), so a
      // hardcoded localhost entry below would silently break those services inside
      // Docker. Only add an entry here for a service that has no route.ts proxy.
      //
      // Destinations below read *_SERVICE_URL env vars. Convention (standardized
      // 2026-07-24): the fallback is the Docker Compose service hostname, matching
      // the route handlers under app/svc/** and app/api/**. This is what production
      // and any Docker deployment use. Consequence: running `npm run dev` directly
      // on the host (outside Docker) requires setting the *_SERVICE_URL env vars —
      // the bare "localhost" fallbacks that used to serve host-only dev are gone.
      //
      // IMPORTANT: setting *_SERVICE_URL only in docker-compose.yaml's `web` service
      // `environment:` block is NOT enough for this rewrites() function specifically
      // (confirmed via debug logging that never fired, despite `docker exec ... echo
      // $VAR` showing the runtime env var correctly set) — it must ALSO be present in
      // apps/web/.env (baked into the image at build time via Next's own env loading,
      // which something about this rewrites()/Turbopack code path depends on instead
      // of — or in addition to — the live process.env). Route handlers (app/api/**/
      // route.ts, app/svc/**/route.ts) don't have this issue; they read process.env
      // normally per-request and only need the docker-compose env var.
      { source: '/svc/sales/:path*', destination: `${process.env.SALES_SERVICE_URL || 'http://sales:8002'}/:path*` },
      { source: '/svc/rica/:path*', destination: `${process.env.RICA_SERVICE_URL || 'http://rica:8004'}/:path*` },
      { source: '/svc/network/:path*', destination: `${process.env.NETWORK_SERVICE_URL || 'http://network:8005'}/:path*` },
      { source: '/svc/iot/:path*', destination: `${process.env.IOT_SERVICE_URL || 'http://iot:8006'}/:path*` },
      // /svc/call-center is handled by app/svc/call-center/[...path]/route.ts
      // (route handler — NOT a rewrite — so long STT/TTS model-load waits
      // don't hit the rewrite proxy's connection limits / ECONNRESET).
      { source: '/svc/support/:path*', destination: `${process.env.SUPPORT_SERVICE_URL || 'http://support:8008'}/:path*` },
      { source: '/svc/hr/:path*', destination: `${process.env.HR_SERVICE_URL || 'http://hr:8009'}/:path*` },
      // NOTE: ANALYTICS_SERVICE_URL (8011) has no service in docker-compose.yaml —
      // it's legacy/unwired, so there is no Docker hostname to fall back to. Left on
      // localhost intentionally; remove this route (or add the service) when resolved.
      { source: '/svc/analytics/:path*', destination: `${process.env.ANALYTICS_SERVICE_URL || 'http://localhost:8011'}/:path*` },
      { source: '/svc/retention/:path*', destination: `${process.env.RETENTION_SERVICE_URL || 'http://retention:8012'}/:path*` },
      { source: '/svc/admin/:path*', destination: `${process.env.ADMIN_SERVICE_URL || 'http://admin:8013'}/:path*` },
      { source: '/svc/communication/:path*', destination: `${process.env.COMMUNICATION_SERVICE_URL || 'http://communication:8020'}/:path*` },
      { source: '/svc/agents/:path*', destination: `${process.env.ORCHESTRATOR_URL || 'http://agent-orchestrator:8021'}/:path*` },
      { source: '/svc/web-analytics/:path*', destination: `${process.env.WEB_ANALYTICS_SERVICE_URL || 'http://web_analytics:8016'}/:path*` },
      { source: '/svc/customer-journey/:path*', destination: `${process.env.CUSTOMER_JOURNEY_SERVICE_URL || 'http://customer_journey:8022'}/:path*` },
      { source: '/svc/billing-collections/:path*', destination: `${process.env.BILLING_COLLECTIONS_SERVICE_URL || 'http://billing_collections:8023'}/:path*` },
      { source: '/svc/fno-intelligence/:path*', destination: `${process.env.FNO_INTELLIGENCE_SERVICE_URL || 'http://fno_intelligence:8024'}/:path*` },
      // /svc/voicebox is handled by app/svc/voicebox/[...path]/route.ts
      // (route handler — NOT a rewrite — so long TTS generation waits
      // don't hit the rewrite proxy's connection limits / ECONNRESET).
    ]
  },
}

export default nextConfig

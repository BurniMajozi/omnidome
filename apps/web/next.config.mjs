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
      { source: '/svc/sales/:path*', destination: 'http://localhost:8002/:path*' },
      { source: '/svc/rica/:path*', destination: 'http://localhost:8004/:path*' },
      { source: '/svc/network/:path*', destination: 'http://localhost:8005/:path*' },
      { source: '/svc/iot/:path*', destination: 'http://localhost:8006/:path*' },
      { source: '/svc/call-center/:path*', destination: 'http://localhost:8007/:path*' },
      { source: '/svc/support/:path*', destination: 'http://localhost:8008/:path*' },
      { source: '/svc/hr/:path*', destination: 'http://localhost:8009/:path*' },
      { source: '/svc/analytics/:path*', destination: 'http://localhost:8011/:path*' },
      { source: '/svc/retention/:path*', destination: 'http://localhost:8012/:path*' },
      { source: '/svc/admin/:path*', destination: 'http://localhost:8013/:path*' },
      { source: '/svc/communication/:path*', destination: 'http://localhost:8020/:path*' },
      { source: '/svc/agents/:path*', destination: 'http://localhost:8021/:path*' },
      { source: '/svc/web-analytics/:path*', destination: 'http://localhost:8016/:path*' },
      { source: '/svc/customer-journey/:path*', destination: 'http://localhost:8022/:path*' },
      { source: '/svc/billing-collections/:path*', destination: 'http://localhost:8023/:path*' },
      { source: '/svc/fno-intelligence/:path*', destination: 'http://localhost:8024/:path*' },
      { source: '/svc/voicebox/:path*', destination: 'http://localhost:8027/:path*' },
    ]
  },
}

export default nextConfig

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
      { source: '/gateway/:path*', destination: 'http://gateway:8000/:path*' },
      // Individual microservice proxies
      { source: '/svc/crm/:path*',         destination: 'http://crm:8001/:path*' },
      { source: '/svc/sales/:path*',        destination: 'http://sales:8002/:path*' },
      { source: '/svc/billing/:path*',      destination: 'http://billing:8003/:path*' },
      { source: '/svc/rica/:path*',         destination: 'http://rica:8004/:path*' },
      { source: '/svc/network/:path*',      destination: 'http://network:8005/:path*' },
      { source: '/svc/iot/:path*',          destination: 'http://iot:8006/:path*' },
      { source: '/svc/call-center/:path*',  destination: 'http://call_center:8007/:path*' },
      { source: '/svc/support/:path*',      destination: 'http://support:8008/:path*' },
      { source: '/svc/hr/:path*',           destination: 'http://hr:8009/:path*' },
      { source: '/svc/inventory/:path*',    destination: 'http://inventory:8010/:path*' },
      { source: '/svc/analytics/:path*',    destination: 'http://analytics:8011/:path*' },
      { source: '/svc/retention/:path*',    destination: 'http://retention:8012/:path*' },
      { source: '/svc/admin/:path*',        destination: 'http://admin:8013/:path*' },
      { source: '/svc/communication/:path*', destination: 'http://communication:8020/:path*' },
      { source: '/svc/agents/:path*',       destination: 'http://agent-orchestrator:8021/:path*' },
      // Journey Engine and lifecycle patches
      { source: '/api/journey-engine/:path*', destination: 'http://journey_engine:8017/:path*' },
      { source: '/api/lifecycle/:path*', destination: 'http://lifecycle:8018/:path*' },
    ]
  },
}

export default nextConfig

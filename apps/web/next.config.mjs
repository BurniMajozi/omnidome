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
      { source: '/svc/crm/:path*',         destination: 'http://localhost:8001/:path*' },
      { source: '/svc/sales/:path*',        destination: 'http://localhost:8002/:path*' },
      { source: '/svc/billing/:path*',      destination: 'http://localhost:8003/:path*' },
      { source: '/svc/rica/:path*',         destination: 'http://localhost:8004/:path*' },
      { source: '/svc/network/:path*',      destination: 'http://localhost:8005/:path*' },
      { source: '/svc/iot/:path*',          destination: 'http://localhost:8006/:path*' },
      { source: '/svc/call-center/:path*',  destination: 'http://localhost:8011/:path*' },
      { source: '/svc/support/:path*',      destination: 'http://localhost:8008/:path*' },
      { source: '/svc/hr/:path*',           destination: 'http://localhost:8009/:path*' },
      { source: '/svc/inventory/:path*',    destination: 'http://localhost:8010/:path*' },
      { source: '/svc/analytics/:path*',    destination: 'http://localhost:8011/:path*' },
      { source: '/svc/retention/:path*',    destination: 'http://localhost:8012/:path*' },
      { source: '/svc/admin/:path*',        destination: 'http://localhost:8013/:path*' },
    ]
  },
}

export default nextConfig

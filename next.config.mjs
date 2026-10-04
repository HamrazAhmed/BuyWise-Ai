/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      { source: '/start', destination: '/' },
      { source: '/research', destination: '/' },
      { source: '/results/:id', destination: '/' },
      { source: '/product/:id', destination: '/' },
    ]
  },
}

export default nextConfig

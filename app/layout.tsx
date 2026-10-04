import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import localFont from 'next/font/local'
import './globals.css'

const sans = localFont({ src: './fonts/UbuntuSans.woff2', variable: '--font-buywise-sans', weight: '100 900', display: 'swap' })
const editorial = localFont({ src: './fonts/NotoSerif.woff2', variable: '--font-editorial', weight: '400', display: 'swap' })

export const metadata: Metadata = {
  title: 'BuyWise AI — Evidence-backed purchase decisions',
  description: 'Research your next purchase. Compare laptops against your priorities, with source-backed facts and clear trade-offs.',
  icons: {
    icon: [{ url: '/buywise-icon.svg', type: 'image/svg+xml' }],
  },
}

export const viewport: Viewport = {
  colorScheme: 'light dark',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f5f4ee' },
    { media: '(prefers-color-scheme: dark)', color: '#18231e' },
  ],
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${editorial.variable} antialiased`}>
        {children}
        {process.env.VERCEL === '1' && <Analytics />}
      </body>
    </html>
  )
}

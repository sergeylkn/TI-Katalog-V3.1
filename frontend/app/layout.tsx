import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'TI-Katalог — Промислові шланги та арматура',
  description: 'Каталог промислових шлангів, арматури, гідравліки та пневматики Tubes International',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uk">
      <body>{children}</body>
    </html>
  )
}

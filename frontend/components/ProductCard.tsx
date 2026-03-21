'use client'
import Link from 'next/link'
import { useState } from 'react'
import type { Product } from '@/lib/api'

const API = process.env.NEXT_PUBLIC_API_URL || ''

export default function ProductCard({ product: p }: { product: Product }) {
  const [imgErr, setImgErr] = useState(false)
  const [imgLoaded, setImgLoaded] = useState(false)

  // Always try to show image if product has page_number
  const hasImg = (p.image_url || p.page_number) && !imgErr
  const imgSrc = `${API}/api/products/${p.id}/image`

  return (
    <Link href={`/product/${p.id}`} className="prod-card">
      <div className="prod-img">
        {hasImg ? (
          <>
            {/* Skeleton while loading */}
            {!imgLoaded && (
              <div style={{
                position: 'absolute', inset: 0,
                background: 'linear-gradient(90deg, var(--bg2) 25%, var(--bg) 50%, var(--bg2) 75%)',
                backgroundSize: '200% 100%',
                animation: 'shimmer 1.2s infinite',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <span style={{ fontSize: 24, opacity: 0.3 }}>📄</span>
              </div>
            )}
            <img
              src={imgSrc}
              alt={p.title}
              loading="lazy"
              onLoad={() => setImgLoaded(true)}
              onError={() => setImgErr(true)}
              style={{
                width: '100%', height: '100%', objectFit: 'contain',
                padding: 8, opacity: imgLoaded ? 1 : 0,
                transition: 'opacity 0.3s',
              }}
            />
          </>
        ) : (
          <div className="prod-img-placeholder">
            <span className="prod-img-icon">📦</span>
            <span style={{ fontSize: 11 }}>{p.title.slice(0, 20)}</span>
          </div>
        )}
        <span className="prod-zoom">🔍 PDF</span>
      </div>
      <div className="prod-body">
        {p.sku && <span className="prod-sku">{p.sku}</span>}
        <div className="prod-title">{p.title}</div>
        {p.subtitle && <div className="prod-sub">{p.subtitle}</div>}
        {Object.keys(p.attributes || {}).length > 0 && (
          <div className="prod-attrs">
            {Object.entries(p.attributes)
              .filter(([k]) => !['Темп_мін','Темп_макс','Тиск_бар','d_вн_мм','d_зовн_мм'].includes(k))
              .slice(0, 3)
              .map(([k, v]) => (
                <span key={k} className="prod-attr">{String(v).slice(0, 30)}</span>
              ))}
          </div>
        )}
      </div>
    </Link>
  )
}

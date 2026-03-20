'use client'
import Link from 'next/link'
import { useState } from 'react'
import type { Product } from '@/lib/api'
import { api } from '@/lib/api'

export default function ProductCard({ product: p }: { product: Product }) {
  const [imgErr, setImgErr] = useState(false)

  return (
    <Link href={`/product/${p.id}`} className="prod-card">
      <div className="prod-img">
        {p.image_url && !imgErr ? (
          <img
            src={api.imageUrl(p.id)}
            alt={p.title}
            onError={() => setImgErr(true)}
            loading="lazy"
          />
        ) : (
          <div className="prod-img-placeholder">
            <span className="prod-img-icon">📄</span>
            <span>{p.page_number ? `Ст. ${p.page_number}` : 'PDF'}</span>
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
            {Object.entries(p.attributes).slice(0, 3).map(([k, v]) => (
              <span key={k} className="prod-attr">{String(v).slice(0, 28)}</span>
            ))}
          </div>
        )}
      </div>
    </Link>
  )
}

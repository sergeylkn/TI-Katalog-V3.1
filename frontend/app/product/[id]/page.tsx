'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ProductCard from '@/components/ProductCard'
import PdfModal from '@/components/PdfModal'
import ChatWidget from '@/components/ChatWidget'
import { api, type Product } from '@/lib/api'

export default function ProductPage() {
  const { id } = useParams<{ id: string }>()
  const [p, setP] = useState<Product | null>(null)
  const [recs, setRecs] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [imgErr, setImgErr] = useState(false)
  const [pdfOpen, setPdfOpen] = useState(false)
  const [showAllVariants, setShowAllVariants] = useState(false)

  useEffect(() => {
    if (!id) return
    const numId = Number(id)
    api.getProduct(numId)
      .then(prod => {
        setP(prod)
        setLoading(false)
        api.recommendations(numId).then(r => setRecs(r.recommendations)).catch(() => {})
      })
      .catch(() => setLoading(false))
  }, [id])

  if (loading) return (
    <>
      <Navbar />
      <div className="loader-wrap" style={{ minHeight: '60vh' }}><div className="spinner" /></div>
    </>
  )

  if (!p) return (
    <>
      <Navbar />
      <div className="loader-wrap" style={{ minHeight: '60vh' }}>
        <div style={{ textAlign: 'center' }}>
          <p style={{ color: 'var(--text2)', marginBottom: 16 }}>Товар не знайдено</p>
          <Link href="/" className="btn btn-ghost">← Головна</Link>
        </div>
      </div>
    </>
  )

  const attrs = Object.entries(p.attributes || {})
  const variants = p.variants || []
  const variantCols = variants.length > 0
    ? Object.keys(variants[0]).filter(k => k !== '_sku').slice(0, 10)
    : []
  const displayVariants = showAllVariants ? variants : variants.slice(0, 8)
  const pdfUrl = p.document_url
  const imageApiUrl = api.imageUrl(p.id)

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>

        {/* Breadcrumbs */}
        <div className="breadcrumbs">
          <Link href="/">Головна</Link>
          <span className="breadcrumbs-sep">›</span>
          <Link href="/">Каталог</Link>
          <span className="breadcrumbs-sep">›</span>
          <span>{p.title}</span>
        </div>

        {/* Main layout */}
        <div className="product-layout" style={{ marginTop: 16 }}>

          {/* LEFT — image + PDF */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Product image from PDF */}
            <div
              className="product-img-wrap"
              onClick={() => pdfUrl && setPdfOpen(true)}
              title="Клік — відкрити PDF"
            >
              {p.image_url && !imgErr ? (
                <img
                  src={imageApiUrl}
                  alt={p.title}
                  onError={() => setImgErr(true)}
                />
              ) : (
                <div className="product-img-placeholder">
                  <span style={{ fontSize: 52, opacity: .3 }}>📄</span>
                  <span style={{ fontSize: 13 }}>Зображення з PDF</span>
                  {p.page_number && (
                    <span style={{ fontSize: 11, color: 'var(--text3)' }}>Сторінка {p.page_number}</span>
                  )}
                </div>
              )}
              {pdfUrl && (
                <div className="product-pdf-btn">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={e => { e.stopPropagation(); setPdfOpen(true) }}
                  >
                    📄 {p.page_number ? `Відкрити PDF (ст. ${p.page_number})` : 'Відкрити PDF'}
                  </button>
                </div>
              )}
            </div>

            {/* Direct PDF link */}
            {pdfUrl && (
              <a
                href={p.page_number ? `${pdfUrl}#page=${p.page_number}` : pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-ghost"
                style={{ justifyContent: 'center' }}
              >
                Відкрити у новій вкладці ↗
              </a>
            )}
          </div>

          {/* RIGHT — product info */}
          <div className="product-info">
            {p.sku && <div className="product-sku">{p.sku}</div>}
            <h1 className="product-title">{p.title}</h1>
            {p.subtitle && <p className="product-subtitle">{p.subtitle}</p>}

            {/* Technical attributes */}
            {attrs.length > 0 && (
              <div className="attrs-table">
                {attrs.map(([k, v]) => (
                  <div key={k} className="attr-row">
                    <span className="attr-label">{k}</span>
                    <span className="attr-value">{String(v)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Buttons */}
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {pdfUrl && (
                <button className="btn btn-primary" onClick={() => setPdfOpen(true)}>
                  📄 Переглянути PDF
                </button>
              )}
              <Link href="/" className="btn btn-ghost">← Каталог</Link>
            </div>

            {/* Page indicator */}
            {p.page_number && (
              <p style={{ fontSize: 12, color: 'var(--text3)' }}>
                □ Сторінка PDF: {p.page_number}
              </p>
            )}
          </div>
        </div>

        {/* Description */}
        {p.description && (
          <div className="card" style={{ marginTop: 28 }}>
            <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: 20, marginBottom: 12 }}>
              Опис та застосування
            </h2>
            <p style={{ fontSize: 14, lineHeight: 1.75, color: 'var(--text)', whiteSpace: 'pre-line' }}>
              {p.description}
            </p>
          </div>
        )}

        {/* Variants table */}
        {variants.length > 0 && variantCols.length > 0 && (
          <div className="card" style={{ marginTop: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: 20 }}>
                Доступні розміри
                <span style={{ fontSize: 13, fontFamily: 'var(--font-sans)', fontWeight: 400, color: 'var(--text3)', marginLeft: 8 }}>
                  {variants.length} варіантів
                </span>
              </h2>
            </div>
            <div className="variants-table-wrap">
              <table className="variants-table">
                <thead>
                  <tr>{variantCols.map(col => <th key={col}>{col}</th>)}</tr>
                </thead>
                <tbody>
                  {displayVariants.map((v, i) => (
                    <tr key={i}>
                      {variantCols.map(col => (
                        <td key={col}>{v[col] || '—'}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {variants.length > 8 && (
              <button
                className="btn btn-ghost btn-sm"
                style={{ marginTop: 12 }}
                onClick={() => setShowAllVariants(!showAllVariants)}
              >
                {showAllVariants ? '▲ Згорнути' : `▼ Показати всі ${variants.length} варіантів`}
              </button>
            )}
          </div>
        )}

        {/* Certifications */}
        {p.certifications && (
          <div className="cert-block" style={{ marginTop: 20 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <span style={{ fontSize: 16 }}>🛡</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Сертифікати та стандарти</div>
                <div>{p.certifications}</div>
              </div>
            </div>
          </div>
        )}

        {/* Recommendations */}
        {recs.length > 0 && (
          <div style={{ marginTop: 40 }}>
            <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: 24, marginBottom: 16 }}>
              Схожі товари
            </h2>
            <div className="prod-grid">
              {recs.map(r => <ProductCard key={r.id} product={r} />)}
            </div>
          </div>
        )}
      </div>

      {/* PDF Modal */}
      {pdfOpen && (
        <PdfModal
          docId={p.document_id}
          pageNumber={p.page_number || 1}
          title={p.title}
          pdfUrl={pdfUrl || undefined}
          onClose={() => setPdfOpen(false)}
        />
      )}

      <footer className="footer">
        <p>© 2025 TI-Katalог · Tubes International Україна</p>
      </footer>
      <ChatWidget />
    </>
  )
}

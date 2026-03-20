'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ProductCard from '@/components/ProductCard'
import ChatWidget from '@/components/ChatWidget'
import { api, type Product } from '@/lib/api'

export default function SectionPage() {
  const { slug, subsection } = useParams<{ slug: string; subsection: string }>()
  const [products, setProducts] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [sectionName, setSectionName] = useState('')
  const [catName, setCatName] = useState('')
  const [loading, setLoading] = useState(true)
  const PAGE_SIZE = 24

  useEffect(() => {
    if (!subsection) return
    setLoading(true)
    api.getProductsBySection(subsection, page, PAGE_SIZE)
      .then(r => {
        setProducts(r.items)
        setTotal(r.total)
        if (r.section) setSectionName(r.section.name)
      })
      .catch(() => setProducts([]))
      .finally(() => setLoading(false))
  }, [subsection, page])

  useEffect(() => {
    if (!slug) return
    api.getCategory(slug).then(c => setCatName(c.name)).catch(() => {})
  }, [slug])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingTop: 24 }}>
        <div className="breadcrumbs">
          <Link href="/">Головна</Link>
          <span className="breadcrumbs-sep">›</span>
          <Link href={`/catalog/${slug}`}>{catName || slug}</Link>
          <span className="breadcrumbs-sep">›</span>
          <span>{sectionName || subsection}</span>
        </div>

        <div className="section-header" style={{ marginTop: 8, marginBottom: 24 }}>
          <h1 className="section-title">{sectionName || subsection}</h1>
          <p className="section-desc">{total} товарів</p>
        </div>

        {loading ? (
          <div className="loader-wrap"><div className="spinner" /></div>
        ) : products.length === 0 ? (
          <div className="loader-wrap"><p style={{ color: 'var(--text2)' }}>Товарів не знайдено</p></div>
        ) : (
          <>
            <div className="prod-grid" style={{ marginBottom: 32 }}>
              {products.map(p => <ProductCard key={p.id} product={p} />)}
            </div>
            {totalPages > 1 && (
              <div className="pagination" style={{ marginBottom: 48 }}>
                <button className="page-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>◀</button>
                {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                  const pg = page <= 4 ? i + 1 : page - 3 + i
                  if (pg < 1 || pg > totalPages) return null
                  return (
                    <button key={pg} className={`page-btn ${pg === page ? 'active' : ''}`}
                      onClick={() => setPage(pg)}>{pg}</button>
                  )
                })}
                <button className="page-btn" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>▶</button>
              </div>
            )}
          </>
        )}
      </div>
      <footer className="footer"><p>© 2025 TI-Katalög · Tubes International Україна</p></footer>
      <ChatWidget />
    </>
  )
}

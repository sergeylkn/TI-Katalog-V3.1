'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ProductCard from '@/components/ProductCard'
import ChatWidget from '@/components/ChatWidget'
import { api, type Product } from '@/lib/api'
import { useLang } from '@/lib/useLang'
import { categoryName, sectionName, t } from '@/lib/translations'

export default function SectionPage() {
  const { slug, subsection } = useParams<{ slug: string; subsection: string }>()
  const [lang] = useLang()
  const [products, setProducts] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const PAGE_SIZE = 24

  useEffect(() => {
    if (!subsection) return
    setLoading(true)
    api.getProductsBySection(subsection, page, PAGE_SIZE)
      .then(r => { setProducts(r.items); setTotal(r.total) })
      .catch(() => setProducts([]))
      .finally(() => setLoading(false))
  }, [subsection, page])

  const catTitle = categoryName(slug, lang)
  const secTitle = sectionName(subsection, lang)
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingTop: 24 }}>
        <div className="breadcrumbs">
          <Link href="/">{t('home', lang)}</Link>
          <span className="breadcrumbs-sep">›</span>
          <Link href={`/catalog/${slug}`}>{catTitle}</Link>
          <span className="breadcrumbs-sep">›</span>
          <span>{secTitle}</span>
        </div>

        <div className="section-header" style={{ marginTop: 8, marginBottom: 24 }}>
          <h1 className="section-title">{secTitle}</h1>
          <p className="section-desc">{total} {t('products', lang)}</p>
        </div>

        {loading ? (
          <div className="loader-wrap"><div className="spinner" /></div>
        ) : products.length === 0 ? (
          <div className="loader-wrap"><p style={{ color: 'var(--text2)' }}>{t('noProducts', lang)}</p></div>
        ) : (
          <>
            <div className="prod-grid" style={{ marginBottom: 32 }}>
              {products.map(p => <ProductCard key={p.id} product={p} />)}
            </div>
            {totalPages > 1 && (
              <div className="pagination" style={{ marginBottom: 48 }}>
                <button className="page-btn" disabled={page === 1} onClick={() => { setPage(p => p - 1); window.scrollTo({top:0}) }}>◀</button>
                {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                  const pg = page <= 4 ? i + 1 : page - 3 + i
                  if (pg < 1 || pg > totalPages) return null
                  return (
                    <button key={pg} className={`page-btn ${pg === page ? 'active' : ''}`}
                      onClick={() => { setPage(pg); window.scrollTo({top:0}) }}>{pg}</button>
                  )
                })}
                <button className="page-btn" disabled={page === totalPages} onClick={() => { setPage(p => p + 1); window.scrollTo({top:0}) }}>▶</button>
              </div>
            )}
          </>
        )}
      </div>
      <footer className="footer"><p>© 2025 TI-Katalog · Tubes International Україна</p></footer>
      <ChatWidget />
    </>
  )
}

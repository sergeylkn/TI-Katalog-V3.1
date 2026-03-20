'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ChatWidget from '@/components/ChatWidget'
import { api, type Section } from '@/lib/api'

interface CategoryData {
  id: number; name: string; slug: string; icon: string; sections: Section[]
}

export default function CategoryPage() {
  const { slug } = useParams<{ slug: string }>()
  const [data, setData] = useState<CategoryData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!slug) return
    api.getCategory(slug).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [slug])

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingTop: 24 }}>
        <div className="breadcrumbs">
          <Link href="/">Головна</Link>
          <span className="breadcrumbs-sep">›</span>
          <span>{data?.name || slug}</span>
        </div>

        {loading ? (
          <div className="loader-wrap"><div className="spinner" /></div>
        ) : !data ? (
          <div className="loader-wrap"><p style={{ color: 'var(--text2)' }}>Категорію не знайдено</p></div>
        ) : (
          <>
            <div className="section-header" style={{ marginTop: 8 }}>
              <h1 className="section-title">{data.icon} {data.name}</h1>
              <p className="section-desc">{data.sections.length} підрозділів</p>
            </div>

            <div className="section-list" style={{ marginBottom: 48 }}>
              {data.sections.map(sec => (
                <Link key={sec.id} href={`/catalog/${slug}/${sec.slug}`} className="section-item">
                  <div>
                    <div className="section-item-name">{sec.name}</div>
                    {sec.description && (
                      <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 3 }}>
                        {sec.description.slice(0, 100)}...
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span className="section-item-count">{sec.product_count} товарів</span>
                    <span className="section-item-arrow">›</span>
                  </div>
                </Link>
              ))}
            </div>
          </>
        )}
      </div>
      <footer className="footer"><p>© 2025 TI-Katalог · Tubes International Україна</p></footer>
      <ChatWidget />
    </>
  )
}

'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ChatWidget from '@/components/ChatWidget'
import { api, type Section } from '@/lib/api'
import { useLang } from '@/lib/useLang'
import { categoryName, sectionName, t } from '@/lib/translations'

interface CategoryData {
  id: number; name: string; slug: string; icon: string; sections: Section[]
}

export default function CategoryPage() {
  const { slug } = useParams<{ slug: string }>()
  const [lang] = useLang()
  const [data, setData] = useState<CategoryData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!slug) return
    api.getCategory(slug).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [slug])

  const catTitle = categoryName(slug, lang)

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingTop: 24 }}>
        <div className="breadcrumbs">
          <Link href="/">{t('home', lang)}</Link>
          <span className="breadcrumbs-sep">›</span>
          <span>{catTitle}</span>
        </div>

        {loading ? (
          <div className="loader-wrap"><div className="spinner" /></div>
        ) : !data ? (
          <div className="loader-wrap"><p style={{ color: 'var(--text2)' }}>{t('notFound', lang)}</p></div>
        ) : (
          <>
            <div className="section-header" style={{ marginTop: 8 }}>
              <h1 className="section-title">{data.icon} {catTitle}</h1>
              <p className="section-desc">{data.sections.length} {t('sections', lang)}</p>
            </div>

            <div className="section-list" style={{ marginBottom: 48 }}>
              {data.sections.map(sec => {
                const secTitle = sectionName(sec.slug, lang)
                return (
                  <Link key={sec.id} href={`/catalog/${slug}/${sec.slug}`} className="section-item">
                    <div>
                      <div className="section-item-name">{secTitle}</div>
                      {sec.description && (
                        <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 3 }}>
                          {sec.description.slice(0, 100)}...
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span className="section-item-count">{sec.product_count} {t('products', lang)}</span>
                      <span className="section-item-arrow">›</span>
                    </div>
                  </Link>
                )
              })}
            </div>
          </>
        )}
      </div>
      <footer className="footer"><p>© 2025 TI-Katalog · Tubes International Україна</p></footer>
      <ChatWidget />
    </>
  )
}

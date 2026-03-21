'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ChatWidget from '@/components/ChatWidget'
import { api, type Category } from '@/lib/api'
import { useLang } from '@/lib/useLang'
import { categoryName, t } from '@/lib/translations'

export default function HomePage() {
  const [cats, setCats] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [lang] = useLang()
  const router = useRouter()

  useEffect(() => {
    api.getCategories().then(setCats).catch(() => setCats([])).finally(() => setLoading(false))
  }, [])

  const doSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`)
  }

  return (
    <>
      <Navbar />
      <div className="hero">
        <div className="hero-label">
          {lang === 'ua' ? 'Промисловий каталог · Tubes International' : 'Katalog przemysłowy · Tubes International'}
        </div>
        <h1>
          {lang === 'ua' ? <>Шланги, арматура<br /><em>та з&apos;єднання</em></> : <>Węże, armatura<br /><em>i złącza</em></>}
        </h1>
        <p className="hero-sub">
          {lang === 'ua' ? '189 каталогів · 2000+ товарів · Пошук по SKU, параметрах та описі'
                         : '189 katalogów · 2000+ produktów · Wyszukiwanie po SKU, parametrach i opisie'}
        </p>
        <form className="hero-search" onSubmit={doSearch}>
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder={t('searchPlaceholder', lang)}
          />
          <button type="submit">{t('find', lang)}</button>
        </form>
        <p className="hero-hint">
          {lang === 'ua' ? 'Підтримується: українська · польська · англійська'
                         : 'Obsługiwane: ukraiński · polski · angielski'}
        </p>
      </div>

      <div style={{ background: 'var(--bg)', padding: '48px 0' }}>
        <div className="container">
          <div className="section-header">
            <h2 className="section-title">
              {lang === 'ua' ? 'Категорії каталогу' : 'Kategorie katalogu'}
            </h2>
            <p className="section-desc">
              {lang === 'ua' ? 'Оберіть категорію для перегляду підрозділів та товарів'
                             : 'Wybierz kategorię, aby przejrzeć poddziały i produkty'}
            </p>
          </div>
          {loading ? (
            <div className="loader-wrap"><div className="spinner" /></div>
          ) : (
            <div className="cat-grid">
              {cats.map(cat => (
                <Link key={cat.id} href={`/catalog/${cat.slug}`} className="cat-card">
                  <span className="cat-icon">{cat.icon || '📦'}</span>
                  <div className="cat-name">{categoryName(cat.slug, lang)}</div>
                  <div className="cat-meta">
                    <span className="cat-count">{cat.section_count} {lang === 'ua' ? 'підрозд.' : 'poddziałów'}</span>
                    <span className="cat-count">·</span>
                    <span className="cat-count">{cat.product_count} {lang === 'ua' ? 'товарів' : 'produktów'}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      <footer className="footer"><p>© 2025 TI-Katalog · Tubes International Україна</p></footer>
      <ChatWidget />
    </>
  )
}

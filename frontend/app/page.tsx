'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ChatWidget from '@/components/ChatWidget'
import { api, type Category } from '@/lib/api'

export default function HomePage() {
  const [cats, setCats] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
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

      {/* Hero */}
      <div className="hero">
        <div className="hero-label">Промисловий каталог · Tubes International</div>
        <h1>Шланги, арматура<br /><em>та з&apos;єднання</em></h1>
        <p className="hero-sub">189 каталогів · 2000+ товарів · Пошук по SKU, параметрах та описі</p>
        <form className="hero-search" onSubmit={doSearch}>
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Введіть назву, SKU або параметри... наприклад: шланг харчовий DN25"
          />
          <button type="submit">Знайти</button>
        </form>
        <p className="hero-hint">Підтримується: українська · польська · англійська</p>
      </div>

      {/* Categories */}
      <div style={{ background: 'var(--bg)', padding: '48px 0' }}>
        <div className="container">
          <div className="section-header">
            <h2 className="section-title">Категорії каталогу</h2>
            <p className="section-desc">Оберіть категорію для перегляду підрозділів та товарів</p>
          </div>

          {loading ? (
            <div className="loader-wrap"><div className="spinner" /></div>
          ) : (
            <div className="cat-grid">
              {cats.map(cat => (
                <Link key={cat.id} href={`/catalog/${cat.slug}`} className="cat-card">
                  <span className="cat-icon">{cat.icon || '📦'}</span>
                  <div className="cat-name">{cat.name}</div>
                  <div className="cat-meta">
                    <span className="cat-count">{cat.section_count} підрозд.</span>
                    <span className="cat-count">·</span>
                    <span className="cat-count">{cat.product_count} товарів</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      <footer className="footer">
        <p>© 2025 TI-Katalог · Tubes International Україна</p>
      </footer>

      <ChatWidget />
    </>
  )
}

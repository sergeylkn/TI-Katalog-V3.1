'use client'
import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'

const T: Record<string, Record<string, string>> = {
  ua: {
    catalog: 'Каталог', search: 'Пошук...', hint: 'UA · PL · EN',
    placeholder: 'Пошук: шланг DN65, FT-CRISTALLO...',
    shop: 'Онлайн магазин →', contact: 'tubes@tubes-international.com',
  },
  pl: {
    catalog: 'Katalog', search: 'Szukaj...', hint: 'UA · PL · EN',
    placeholder: 'Szukaj: wąż DN65, FT-CRISTALLO...',
    shop: 'Sklep online →', contact: 'tubes@tubes-international.com',
  },
}

export default function Navbar() {
  const [lang, setLang] = useState<'ua'|'pl'>('ua')
  const [dark, setDark] = useState(false)
  const [q, setQ] = useState('')
  const [suggs, setSuggs] = useState<any[]>([])
  const [suggOpen, setSuggOpen] = useState(false)
  const router = useRouter()
  const timer = useRef<any>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  const t = T[lang]

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    if (q.length < 2) { setSuggs([]); setSuggOpen(false); return }
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      try {
        const r = await api.suggest(q)
        setSuggs(r.suggestions || [])
        setSuggOpen(r.suggestions.length > 0)
      } catch {}
    }, 300)
  }, [q])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setSuggOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const doSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`)
    setSuggOpen(false)
  }

  return (
    <>
      {/* Top bar */}
      <div className="topbar">
        <span>📍 {lang === 'ua' ? 'Промисловий каталог · Україна' : 'Katalog przemysłowy · Ukraina'}</span>
        <div className="topbar-right">
          <a href="mailto:tubes@tubes-international.com">{t.contact}</a>
          <a href="https://sklep.tubes-international.pl" target="_blank" rel="noopener noreferrer" className="topbar-shop">{t.shop}</a>
        </div>
      </div>

      {/* Main navbar */}
      <nav className="navbar">
        <Link href="/" className="nav-logo">TI<span>·</span>Каталог</Link>

        <div className="nav-links">
          <Link href="/" className="nav-link">{t.catalog}</Link>
          <Link href="/catalog/shlanhy-dlya-promyslovosti" className="nav-link">
            {lang === 'ua' ? 'Шланги' : 'Węże'}
          </Link>
          <Link href="/catalog/promyslova-armatura" className="nav-link">
            {lang === 'ua' ? 'Арматура' : 'Armatura'}
          </Link>
          <Link href="/catalog/sylova-hidravlika" className="nav-link">
            {lang === 'ua' ? 'Гідравліка' : 'Hydraulika'}
          </Link>
          <Link href="/catalog/promyslova-pnevmatyka" className="nav-link">
            {lang === 'ua' ? 'Пневматика' : 'Pneumatyka'}
          </Link>
        </div>

        {/* Search */}
        <div className="nav-search" ref={wrapRef}>
          <form onSubmit={doSearch}>
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder={t.placeholder}
              autoComplete="off"
            />
            <button type="submit" className="nav-search-btn">⌕</button>
          </form>
          <div className={`search-suggestions ${suggOpen ? 'open' : ''}`}>
            {suggs.map((s, i) => (
              <div key={i} className="sugg-item" onClick={() => {
                router.push(`/product/${s.id}`)
                setSuggOpen(false)
                setQ(s.title)
              }}>
                <span className="sugg-type">{s.sku ? 'SKU' : 'Товар'}</span>
                <span>{s.title}</span>
                {s.sku && <span className="sugg-sku">{s.sku}</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Controls */}
        <div className="nav-controls">
          <button className={`lang-btn ${lang === 'ua' ? 'active' : ''}`} onClick={() => setLang('ua')}>
            🇺🇦 UA
          </button>
          <button className={`lang-btn ${lang === 'pl' ? 'active' : ''}`} onClick={() => setLang('pl')}>
            🇵🇱 PL
          </button>
          <button className="theme-btn" onClick={() => setDark(!dark)}>
            {dark ? '☀️' : '🌙'}
          </button>
        </div>
      </nav>
    </>
  )
}

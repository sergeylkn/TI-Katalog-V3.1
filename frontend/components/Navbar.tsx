'use client'
import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useLang } from '@/lib/useLang'
import { t, categoryName } from '@/lib/translations'

export default function Navbar() {
  const [lang, setLang] = useLang()
  const [dark, setDark] = useState(false)
  const [q, setQ] = useState('')
  const [suggs, setSuggs] = useState<any[]>([])
  const [suggOpen, setSuggOpen] = useState(false)
  const router = useRouter()
  const timer = useRef<any>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    const saved = localStorage.getItem('ti_dark')
    if (saved === '1') setDark(true)
  }, [])

  const toggleDark = () => {
    const next = !dark
    setDark(next)
    localStorage.setItem('ti_dark', next ? '1' : '0')
  }

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
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node))
        setSuggOpen(false)
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
      <div className="topbar">
        <span>📍 {t('topbar', lang)}</span>
        <div className="topbar-right">
          <a href="mailto:tubes@tubes-international.com">tubes@tubes-international.com</a>
          <a href="https://sklep.tubes-international.pl" target="_blank" rel="noopener noreferrer" className="topbar-shop">
            {t('shop', lang)}
          </a>
        </div>
      </div>

      <nav className="navbar">
        <Link href="/" className="nav-logo">TI<span>·</span>Каталог</Link>

        <div className="nav-links">
          <Link href="/" className="nav-link">{t('catalog', lang)}</Link>
          <Link href="/catalog/shlanhy-dlya-promyslovosti" className="nav-link">{t('hoses', lang)}</Link>
          <Link href="/catalog/promyslova-armatura" className="nav-link">{t('fittings', lang)}</Link>
          <Link href="/catalog/sylova-hidravlika" className="nav-link">{t('hydraulics', lang)}</Link>
          <Link href="/catalog/promyslova-pnevmatyka" className="nav-link">{t('pneumatics', lang)}</Link>
        </div>

        <div className="nav-search" ref={wrapRef}>
          <form onSubmit={doSearch}>
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder={t('searchPlaceholder', lang)}
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
                <span className="sugg-type">{s.sku ? 'SKU' : t('catalog', lang)}</span>
                <span>{s.title}</span>
                {s.sku && <span className="sugg-sku">{s.sku}</span>}
              </div>
            ))}
          </div>
        </div>

        <div className="nav-controls">
          <button className={`lang-btn ${lang === 'ua' ? 'active' : ''}`} onClick={() => setLang('ua')}>
            🇺🇦 UA
          </button>
          <button className={`lang-btn ${lang === 'pl' ? 'active' : ''}`} onClick={() => setLang('pl')}>
            🇵🇱 PL
          </button>
          <button className="theme-btn" onClick={toggleDark}>
            {dark ? '☀️' : '🌙'}
          </button>
        </div>
      </nav>
    </>
  )
}

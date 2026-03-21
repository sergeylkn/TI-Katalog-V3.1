'use client'
import { useEffect, useState, useRef } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ProductCard from '@/components/ProductCard'
import ChatWidget from '@/components/ChatWidget'
import { api, type SearchResult } from '@/lib/api'
import { useLang } from '@/lib/useLang'
import { t } from '@/lib/translations'

const API = process.env.NEXT_PUBLIC_API_URL || ''
const PAGE_SIZE = 20

interface AiRec {
  advice: string
  params: Record<string, string>
  products: Array<{ id: number; title: string; sku: string; image_url: string; attributes: Record<string, string> }>
}

export default function SearchInner() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [lang] = useLang()
  const q = searchParams.get('q') || ''

  const [results, setResults]       = useState<SearchResult[]>([])
  const [total, setTotal]           = useState(0)
  const [loading, setLoading]       = useState(false)
  const [vectorUsed, setVectorUsed] = useState(false)
  const [paramsDetected, setParams] = useState<any>({})
  const [inputQ, setInputQ]         = useState(q)
  const [page, setPage]             = useState(1)

  // AI recommendation state
  const [aiRec, setAiRec]           = useState<AiRec | null>(null)
  const [aiLoading, setAiLoading]   = useState(false)
  const aiTimer                     = useRef<any>(null)

  // Reset page on query change
  useEffect(() => { setInputQ(q); setPage(1) }, [q])

  // Fetch results when q or page changes
  useEffect(() => {
    if (!q) { setResults([]); setTotal(0); return }
    setLoading(true)
    api.search(q, page, PAGE_SIZE)
      .then(r => {
        setResults(r.items)
        setTotal(r.total)
        setVectorUsed(r.vector_used)
        setParams(r.params_detected || {})
        window.scrollTo({ top: 0, behavior: 'smooth' })
      })
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [q, page])

  // Fetch AI recommendation when q changes (debounced)
  useEffect(() => {
    if (!q || q.length < 3) { setAiRec(null); return }
    clearTimeout(aiTimer.current)
    setAiLoading(true)
    aiTimer.current = setTimeout(async () => {
      try {
        const r = await fetch(`${API}/api/search/ai-recommend?q=${encodeURIComponent(q)}`)
        const data = await r.json()
        setAiRec(data)
      } catch { setAiRec(null) }
      finally { setAiLoading(false) }
    }, 600)
    return () => clearTimeout(aiTimer.current)
  }, [q])

  const doSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (inputQ.trim()) {
      setPage(1)
      router.push(`/search?q=${encodeURIComponent(inputQ.trim())}`)
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const hasParams = Object.keys(paramsDetected).length > 0

  const pageNums = () => {
    const nums = []
    const start = Math.max(1, page - 2)
    const end   = Math.min(totalPages, page + 2)
    for (let i = start; i <= end; i++) nums.push(i)
    return nums
  }

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>

        {/* Search bar */}
        <form onSubmit={doSearch} style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
          <input
            value={inputQ}
            onChange={e => setInputQ(e.target.value)}
            placeholder={t('searchPlaceholder', lang)}
            style={{
              flex: 1, padding: '12px 18px', fontSize: 15,
              background: 'var(--card)', border: '1.5px solid var(--border2)',
              borderRadius: 'var(--radius)', color: 'var(--text)',
              fontFamily: 'var(--font-sans)', outline: 'none',
            }}
          />
          <button type="submit" className="btn btn-primary" style={{ padding: '12px 28px', fontSize: 15 }}>
            {t('find', lang)}
          </button>
        </form>

        {/* ── AI RECOMMENDATION PANEL ── */}
        {q && (aiLoading || aiRec) && (
          <div style={{
            background: 'var(--card)', border: '1px solid var(--border2)',
            borderLeft: '3px solid var(--accent)',
            borderRadius: 'var(--radius2)', padding: '16px 20px',
            marginBottom: 20,
          }}>
            {/* AI header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <span style={{ fontSize: 18 }}>🔧</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
                {lang === 'ua' ? 'AI Консультант · Тарас' : 'AI Doradca · Taras'}
              </span>
              {aiLoading && <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2, marginLeft: 4 }} />}
              {aiRec?.params && Object.keys(aiRec.params).length > 0 && (
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {Object.entries(aiRec.params).map(([k, v]) => (
                    <span key={k} style={{
                      fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 700,
                      background: 'var(--accent-bg)', color: 'var(--accent)',
                      padding: '2px 7px', borderRadius: 3,
                    }}>{k}={v}</span>
                  ))}
                </div>
              )}
            </div>

            {/* AI advice text */}
            {aiRec?.advice && (
              <p style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.7, marginBottom: 14 }}>
                {aiRec.advice}
              </p>
            )}

            {/* Top product cards from AI */}
            {aiRec?.products && aiRec.products.length > 0 && (
              <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
                {aiRec.products.map(p => (
                  <a key={p.id} href={`/product/${p.id}`} style={{ textDecoration: 'none', flexShrink: 0 }}>
                    <div style={{
                      width: 130, background: 'var(--bg2)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)', overflow: 'hidden',
                      transition: 'box-shadow .15s, border-color .15s',
                      cursor: 'pointer',
                    }}
                      onMouseEnter={e => {
                        (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--accent)'
                        ;(e.currentTarget as HTMLDivElement).style.boxShadow = '0 2px 10px rgba(196,30,30,.2)'
                      }}
                      onMouseLeave={e => {
                        (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border)'
                        ;(e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
                      }}
                    >
                      {/* Thumbnail */}
                      <div style={{
                        height: 80, background: 'white',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        overflow: 'hidden',
                      }}>
                        {p.image_url ? (
                          <img src={`${API}${p.image_url}`} alt={p.title}
                            style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 4 }}
                            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                        ) : (
                          <span style={{ fontSize: 24, opacity: 0.3 }}>📦</span>
                        )}
                      </div>
                      {/* Info */}
                      <div style={{ padding: '6px 8px' }}>
                        {p.sku && <div style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--accent)', marginBottom: 2 }}>{p.sku}</div>}
                        <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text)', lineHeight: 1.3,
                          overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                          {p.title}
                        </div>
                        {p.attributes?.DN && (
                          <div style={{ fontSize: 9, color: 'var(--text3)', marginTop: 2 }}>DN{p.attributes.DN}</div>
                        )}
                      </div>
                    </div>
                  </a>
                ))}
                <a href={`/search?q=${encodeURIComponent(q)}`} style={{ textDecoration: 'none', flexShrink: 0, alignSelf: 'center' }}>
                  <div style={{
                    width: 80, height: 80, background: 'var(--accent-bg)',
                    border: '1px dashed var(--accent)', borderRadius: 'var(--radius)',
                    display: 'flex', flexDirection: 'column', alignItems: 'center',
                    justifyContent: 'center', gap: 4, cursor: 'pointer',
                  }}>
                    <span style={{ fontSize: 18, color: 'var(--accent)' }}>→</span>
                    <span style={{ fontSize: 10, color: 'var(--accent)', fontWeight: 600, textAlign: 'center', padding: '0 4px' }}>
                      {lang === 'ua' ? 'Всі результати' : 'Wszystkie'}
                    </span>
                  </div>
                </a>
              </div>
            )}
          </div>
        )}

        {/* Status bar */}
        {q && !loading && total > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 14, color: 'var(--text2)' }}>
              <strong style={{ color: 'var(--text)' }}>{total}</strong> {t('searchResults', lang)} «{q}»
              {totalPages > 1 && <span style={{ marginLeft: 8, color: 'var(--text3)' }}>· {t('page', lang)} {page} {t('of', lang)} {totalPages}</span>}
            </span>
            {vectorUsed && (
              <span style={{ fontSize: 11, background: '#E6F1FB', color: '#185FA5', padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>
                🔮 {t('semanticSearch', lang)}
              </span>
            )}
            {hasParams && (
              <span style={{ fontSize: 12, color: 'var(--text3)' }}>
                {t('detected', lang)}: {Object.entries(paramsDetected).map(([k, v]) => `${k}=${v}`).join(', ')}
              </span>
            )}
          </div>
        )}

        {/* Results grid */}
        {loading ? (
          <div className="loader-wrap" style={{ minHeight: 300 }}><div className="spinner" /></div>
        ) : !q ? (
          <div className="loader-wrap" style={{ minHeight: 300 }}>
            <p style={{ color: 'var(--text3)' }}>{lang === 'ua' ? 'Введіть запит для пошуку' : 'Wpisz zapytanie'}</p>
          </div>
        ) : results.length === 0 && !loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <p style={{ fontSize: 18, color: 'var(--text2)', marginBottom: 8 }}>{t('noResults', lang)}</p>
            <p style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 24 }}>{t('tryOther', lang)}</p>
            <Link href="/" className="btn btn-ghost">{t('backToCatalog', lang)}</Link>
          </div>
        ) : (
          <>
            <div className="prod-grid">
              {results.map(r => (
                <div key={r.id} style={{ position: 'relative' }}>
                  <ProductCard product={r} />
                  {r._match && (
                    <div style={{ position: 'absolute', top: 8, left: 8 }}>
                      <span className={`match-badge match-${r._match}`}>
                        {r._match === 'sku' ? '🎯 SKU' : r._match === 'vector' ? '🔮 AI' : '📝'}
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="pagination" style={{ marginTop: 32 }}>
                <button className="page-btn" disabled={page === 1}
                  onClick={() => { setPage(p => p - 1); window.scrollTo({ top: 0 }) }}>◀</button>

                {page > 3 && <>
                  <button className="page-btn" onClick={() => setPage(1)}>1</button>
                  {page > 4 && <span style={{ padding: '0 6px', color: 'var(--text3)' }}>…</span>}
                </>}

                {pageNums().map(n => (
                  <button key={n} className={`page-btn ${n === page ? 'active' : ''}`}
                    onClick={() => { setPage(n); window.scrollTo({ top: 0 }) }}>{n}</button>
                ))}

                {page < totalPages - 2 && <>
                  {page < totalPages - 3 && <span style={{ padding: '0 6px', color: 'var(--text3)' }}>…</span>}
                  <button className="page-btn" onClick={() => setPage(totalPages)}>{totalPages}</button>
                </>}

                <button className="page-btn" disabled={page >= totalPages}
                  onClick={() => { setPage(p => p + 1); window.scrollTo({ top: 0 }) }}>▶</button>
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

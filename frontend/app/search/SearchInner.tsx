'use client'
import { useEffect, useState, useCallback } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ProductCard from '@/components/ProductCard'
import ChatWidget from '@/components/ChatWidget'
import { api, type SearchResult } from '@/lib/api'

const PAGE_SIZE = 20

export default function SearchInner() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const q = searchParams.get('q') || ''

  const [results, setResults]           = useState<SearchResult[]>([])
  const [total, setTotal]               = useState(0)
  const [loading, setLoading]           = useState(false)
  const [vectorUsed, setVectorUsed]     = useState(false)
  const [paramsDetected, setParams]     = useState<any>({})
  const [inputQ, setInputQ]             = useState(q)
  const [page, setPage]                 = useState(1)

  // Reset to page 1 when query changes
  useEffect(() => {
    setInputQ(q)
    setPage(1)
  }, [q])

  // Fetch when query OR page changes
  useEffect(() => {
    if (!q) { setResults([]); setTotal(0); return }
    setLoading(true)
    api.search(q, page, PAGE_SIZE)
      .then(r => {
        setResults(r.items)
        setTotal(r.total)
        setVectorUsed(r.vector_used)
        setParams(r.params_detected || {})
        // Scroll to top of results
        window.scrollTo({ top: 0, behavior: 'smooth' })
      })
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [q, page])  // ← both q AND page trigger fetch

  const doSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (inputQ.trim()) {
      setPage(1)
      router.push(`/search?q=${encodeURIComponent(inputQ.trim())}`)
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const hasParams = Object.keys(paramsDetected).length > 0

  // Page number range to show
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
        <form onSubmit={doSearch} style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
          <input
            value={inputQ}
            onChange={e => setInputQ(e.target.value)}
            placeholder="Пошук по каталогу..."
            style={{
              flex: 1, padding: '11px 16px', fontSize: 14,
              background: 'var(--card)', border: '1px solid var(--border2)',
              borderRadius: 'var(--radius)', color: 'var(--text)',
              fontFamily: 'var(--font-sans)', outline: 'none',
            }}
          />
          <button type="submit" className="btn btn-primary">Знайти</button>
        </form>

        {/* Status bar */}
        {q && !loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 14, color: 'var(--text2)' }}>
              <strong style={{ color: 'var(--text)' }}>{total}</strong> результатів для «{q}»
              {totalPages > 1 && (
                <span style={{ marginLeft: 8, color: 'var(--text3)' }}>
                  · сторінка {page} з {totalPages}
                </span>
              )}
            </span>
            {vectorUsed && (
              <span style={{ fontSize: 11, background: '#E6F1FB', color: '#185FA5', padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>
                🔮 Семантичний пошук
              </span>
            )}
            {hasParams && (
              <span style={{ fontSize: 12, color: 'var(--text3)' }}>
                Виявлено: {Object.entries(paramsDetected).map(([k, v]) => `${k}=${v}`).join(', ')}
              </span>
            )}
          </div>
        )}

        {/* Results */}
        {loading ? (
          <div className="loader-wrap" style={{ minHeight: 300 }}><div className="spinner" /></div>
        ) : !q ? (
          <div className="loader-wrap" style={{ minHeight: 300 }}>
            <p style={{ color: 'var(--text3)' }}>Введіть запит для пошуку</p>
          </div>
        ) : results.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <p style={{ fontSize: 18, color: 'var(--text2)', marginBottom: 8 }}>Нічого не знайдено</p>
            <p style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 24 }}>
              Спробуйте змінити запит або перегляньте каталог
            </p>
            <Link href="/" className="btn btn-ghost">← До каталогу</Link>
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
                        {r._match === 'sku' ? '🎯 SKU' : r._match === 'vector' ? '🔮 AI' : '📝 текст'}
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="pagination" style={{ marginTop: 32, marginBottom: 16 }}>
                <button
                  className="page-btn"
                  disabled={page === 1}
                  onClick={() => setPage(p => p - 1)}
                >◀</button>

                {page > 3 && (
                  <>
                    <button className="page-btn" onClick={() => setPage(1)}>1</button>
                    {page > 4 && <span style={{ padding: '0 4px', color: 'var(--text3)' }}>…</span>}
                  </>
                )}

                {pageNums().map(n => (
                  <button
                    key={n}
                    className={`page-btn ${n === page ? 'active' : ''}`}
                    onClick={() => setPage(n)}
                  >{n}</button>
                ))}

                {page < totalPages - 2 && (
                  <>
                    {page < totalPages - 3 && <span style={{ padding: '0 4px', color: 'var(--text3)' }}>…</span>}
                    <button className="page-btn" onClick={() => setPage(totalPages)}>{totalPages}</button>
                  </>
                )}

                <button
                  className="page-btn"
                  disabled={page >= totalPages}
                  onClick={() => setPage(p => p + 1)}
                >▶</button>
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

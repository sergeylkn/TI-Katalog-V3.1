'use client'
import { useEffect, useState } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import ProductCard from '@/components/ProductCard'
import ChatWidget from '@/components/ChatWidget'
import { api, type SearchResult } from '@/lib/api'

export default function SearchInner() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const q = searchParams.get('q') || ''
  const [results, setResults] = useState<SearchResult[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [vectorUsed, setVectorUsed] = useState(false)
  const [paramsDetected, setParamsDetected] = useState<any>({})
  const [inputQ, setInputQ] = useState(q)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 20

  useEffect(() => {
    setInputQ(q)
    if (!q) return
    setLoading(true)
    setPage(1)
    api.search(q, 1, PAGE_SIZE)
      .then(r => {
        setResults(r.items)
        setTotal(r.total)
        setVectorUsed(r.vector_used)
        setParamsDetected(r.params_detected || {})
      })
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [q])

  const doSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (inputQ.trim()) router.push(`/search?q=${encodeURIComponent(inputQ.trim())}`)
  }

  const hasParams = Object.keys(paramsDetected).length > 0

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>
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

        {q && !loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 14, color: 'var(--text2)' }}>
              <strong style={{ color: 'var(--text)' }}>{total}</strong> результатів для «{q}»
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

        {loading ? (
          <div className="loader-wrap" style={{ minHeight: 300 }}><div className="spinner" /></div>
        ) : !q ? (
          <div className="loader-wrap" style={{ minHeight: 300 }}>
            <p style={{ color: 'var(--text3)' }}>Введіть запит для пошуку</p>
          </div>
        ) : results.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <p style={{ fontSize: 18, color: 'var(--text2)', marginBottom: 8 }}>Нічого не знайдено</p>
            <p style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 24 }}>Спробуйте інший запит або перегляньте каталог</p>
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
            {total > PAGE_SIZE && (
              <div className="pagination" style={{ marginTop: 32 }}>
                <button className="page-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>◀</button>
                <span style={{ fontSize: 13, color: 'var(--text2)', padding: '0 12px' }}>
                  Стор. {page} з {Math.ceil(total / PAGE_SIZE)}
                </span>
                <button className="page-btn" disabled={page >= Math.ceil(total / PAGE_SIZE)} onClick={() => setPage(p => p + 1)}>▶</button>
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

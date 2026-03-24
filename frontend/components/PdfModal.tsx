'use client'
import { useEffect, useState, useRef } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || ''

const SCALES = [1.0, 1.4, 1.8, 2.4, 3.0]

interface Props {
  docId: number
  pageNumber?: number
  pageCount?: number
  title?: string
  pdfUrl?: string
  onClose: () => void
}

export default function PdfModal({ docId, pageNumber = 1, pageCount, title, pdfUrl, onClose }: Props) {
  const [page, setPage] = useState(pageNumber)
  const [scaleIdx, setScaleIdx] = useState(2)   // default 1.8
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const [editingPage, setEditingPage] = useState(false)
  const [pageInput, setPageInput] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const scale = SCALES[scaleIdx]

  useEffect(() => { setPage(pageNumber) }, [pageNumber])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (editingPage) return
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') setPage((p: number) => Math.max(1, p - 1))
      if (e.key === 'ArrowRight') setPage((p: number) => pageCount ? Math.min(pageCount, p + 1) : p + 1)
      if (e.key === '+' || e.key === '=') setScaleIdx((i: number) => Math.min(SCALES.length - 1, i + 1))
      if (e.key === '-') setScaleIdx((i: number) => Math.max(0, i - 1))
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose, pageCount, editingPage])

  useEffect(() => {
    setLoaded(false)
    setError(false)
  }, [page, scale])

  useEffect(() => {
    if (editingPage && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editingPage])

  const prevPage = () => setPage((p: number) => Math.max(1, p - 1))
  const nextPage = () => setPage((p: number) => pageCount ? Math.min(pageCount, p + 1) : p + 1)
  const zoomOut = () => setScaleIdx((i: number) => Math.max(0, i - 1))
  const zoomIn  = () => setScaleIdx((i: number) => Math.min(SCALES.length - 1, i + 1))

  const commitPage = () => {
    const n = parseInt(pageInput, 10)
    if (!isNaN(n) && n >= 1 && (!pageCount || n <= pageCount)) {
      setPage(n)
    }
    setEditingPage(false)
  }

  const imgSrc = `${API}/api/documents/${docId}/page/${page}/image?scale=${scale}`

  return (
    <div className="modal-overlay open" onClick={(e: { target: unknown; currentTarget: unknown }) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal-box" onClick={(e: { stopPropagation: () => void }) => e.stopPropagation()}>

        <div className="modal-header">
          <div className="modal-title">📄 {title || 'PDF'}</div>
          <div className="modal-controls">

            {/* Навігація сторінками */}
            <button className="modal-btn" onClick={prevPage} disabled={page <= 1} title="← Попередня (←)">◀</button>

            {/* Клікабельний номер сторінки */}
            {editingPage ? (
              <input
                ref={inputRef}
                type="number"
                min={1}
                max={pageCount || 9999}
                value={pageInput}
                onChange={(e: { target: { value: string } }) => setPageInput(e.target.value)}
                onBlur={commitPage}
                onKeyDown={(e: { key: string }) => {
                  if (e.key === 'Enter') commitPage()
                  if (e.key === 'Escape') setEditingPage(false)
                }}
                style={{
                  width: 52, textAlign: 'center', fontSize: 12,
                  background: 'var(--bg2)', border: '1px solid var(--accent)',
                  borderRadius: 4, color: 'var(--text)', padding: '2px 4px',
                }}
              />
            ) : (
              <span
                onClick={() => { setPageInput(String(page)); setEditingPage(true) }}
                title="Клікни щоб перейти до сторінки"
                style={{
                  fontSize: 12, color: 'var(--text2)', padding: '0 6px',
                  minWidth: 60, textAlign: 'center', cursor: 'pointer',
                  userSelect: 'none', borderRadius: 4,
                  border: '1px solid transparent',
                }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--border)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'transparent')}
              >
                {page}{pageCount ? ` / ${pageCount}` : ''}
              </span>
            )}

            <button className="modal-btn" onClick={nextPage} disabled={!!pageCount && page >= pageCount} title="Наступна (→) ▶">▶</button>

            {/* Роздільник */}
            <span style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} />

            {/* Зум */}
            <button className="modal-btn" onClick={zoomOut} disabled={scaleIdx === 0} title="Зменшити (-)">−</button>
            <span style={{ fontSize: 11, color: 'var(--text3)', minWidth: 36, textAlign: 'center' }}>
              {Math.round(scale * 100 / 1.8)}%
            </span>
            <button className="modal-btn" onClick={zoomIn} disabled={scaleIdx === SCALES.length - 1} title="Збільшити (+)">+</button>

            {/* Роздільник */}
            <span style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} />

            {pdfUrl && (
              <a
                href={pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="modal-btn"
                title="Завантажити PDF"
              >
                ⬇ PDF
              </a>
            )}
            <button className="modal-close" onClick={onClose}>✕</button>
          </div>
        </div>

        <div
          className="modal-body"
          style={{ position: 'relative', background: '#f0f0f0', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', overflowY: 'auto' }}
        >
          {!loaded && !error && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--bg2)',
            }}>
              <div className="spinner" />
            </div>
          )}
          {error ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text2)' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
              <div>Не вдалося завантажити сторінку {page}</div>
              {pdfUrl && (
                <a href={pdfUrl} target="_blank" rel="noopener noreferrer"
                   className="btn btn-ghost" style={{ marginTop: 16, display: 'inline-block' }}>
                  Відкрити PDF напряму ↗
                </a>
              )}
            </div>
          ) : (
            <img
              key={imgSrc}
              src={imgSrc}
              alt={`Сторінка ${page}`}
              onLoad={() => { setLoaded(true); setError(false) }}
              onError={() => { setError(true); setLoaded(false) }}
              style={{
                maxWidth: '100%',
                objectFit: 'contain',
                display: loaded ? 'block' : 'none',
                boxShadow: '0 2px 16px rgba(0,0,0,0.15)',
              }}
            />
          )}
        </div>

        <div className="modal-footer">
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>
            ← → навігація · +/− зум · клік на номер — перехід до сторінки
          </span>
          {pdfUrl && (
            <a href={pdfUrl} target="_blank" rel="noopener noreferrer"
               style={{ color: 'var(--accent)', fontSize: 12 }}>
              Відкрити PDF у новій вкладці →
            </a>
          )}
        </div>

      </div>
    </div>
  )
}

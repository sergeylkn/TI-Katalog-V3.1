'use client'
import { useEffect, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || ''

interface Props {
  docId: number
  pageNumber?: number
  pageCount?: number
  title?: string
  pdfUrl?: string   // для кнопки "скачать"
  onClose: () => void
}

export default function PdfModal({ docId, pageNumber = 1, pageCount, title, pdfUrl, onClose }: Props) {
  const [page, setPage] = useState(pageNumber)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    setPage(pageNumber)
  }, [pageNumber])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') setPage(p => Math.max(1, p - 1))
      if (e.key === 'ArrowRight') setPage(p => pageCount ? Math.min(pageCount, p + 1) : p + 1)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose, pageCount])

  // Серверный рендер страницы — надёжнее iframe, не зависит от браузерного PDF-плагина
  const imgSrc = `${API}/api/documents/${docId}/page/${page}/image?scale=1.8`

  // При смене страницы сбрасываем статус загрузки
  useEffect(() => {
    setLoaded(false)
    setError(false)
  }, [page])

  const prevPage = () => setPage(p => Math.max(1, p - 1))
  const nextPage = () => setPage(p => pageCount ? Math.min(pageCount, p + 1) : p + 1)

  return (
    <div className="modal-overlay open" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>

        <div className="modal-header">
          <div className="modal-title">📄 {title || 'PDF'}</div>
          <div className="modal-controls">
            <button className="modal-btn" onClick={prevPage} title="← Попередня (←)">◀</button>
            <span style={{ fontSize: 12, color: 'var(--text2)', padding: '0 8px', minWidth: 60, textAlign: 'center' }}>
              Ст. {page}{pageCount ? ` / ${pageCount}` : ''}
            </span>
            <button className="modal-btn" onClick={nextPage} title="Наступна (→) ▶">▶</button>
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

        <div className="modal-body" style={{ position: 'relative', background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {/* Skeleton поки завантажується */}
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
                maxHeight: '100%',
                objectFit: 'contain',
                display: loaded ? 'block' : 'none',
                boxShadow: '0 2px 16px rgba(0,0,0,0.15)',
              }}
            />
          )}
        </div>

        <div className="modal-footer">
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>
            Товар на сторінці: {pageNumber}
            {pageCount && ` · Всього сторінок: ${pageCount}`}
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

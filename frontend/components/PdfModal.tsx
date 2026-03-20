'use client'
import { useEffect, useState } from 'react'

interface Props {
  pdfUrl: string
  pageNumber?: number
  title?: string
  onClose: () => void
}

export default function PdfModal({ pdfUrl, pageNumber = 1, title, onClose }: Props) {
  const [page, setPage] = useState(pageNumber)

  useEffect(() => {
    setPage(pageNumber)
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [pageNumber, onClose])

  // Build URL with page anchor for PDF viewer
  const viewerUrl = `/pdf-viewer.html?file=${encodeURIComponent(pdfUrl)}&page=${page}`
  // Fallback: direct PDF with page
  const directUrl = `${pdfUrl}#page=${page}`

  return (
    <div className="modal-overlay open" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">📄 {title || pdfUrl.split('/').pop()}</div>
          <div className="modal-controls">
            <button className="modal-btn" onClick={() => setPage(p => Math.max(1, p - 1))}>◀</button>
            <span style={{ fontSize: 12, color: 'var(--text2)', padding: '0 8px' }}>Ст. {page}</span>
            <button className="modal-btn" onClick={() => setPage(p => p + 1)}>▶</button>
            <a href={directUrl} target="_blank" rel="noopener noreferrer" className="modal-btn">
              ⬇ Завантажити
            </a>
            <button className="modal-close" onClick={onClose}>✕</button>
          </div>
        </div>
        <div className="modal-body">
          <iframe
            src={directUrl}
            title={title || 'PDF'}
            allow="fullscreen"
          />
        </div>
        <div className="modal-footer">
          <span>Сторінка товару: {pageNumber}</span>
          <a href={directUrl} target="_blank" rel="noopener noreferrer"
             style={{ color: 'var(--accent)', fontSize: 12 }}>
            Відкрити у новій вкладці →
          </a>
        </div>
      </div>
    </div>
  )
}

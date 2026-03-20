'use client'
import { useState, useRef, useEffect } from 'react'
import { api } from '@/lib/api'

interface Msg { role: 'user' | 'assistant'; content: string }

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: 'assistant', content: 'Привіт! Допоможу знайти потрібний товар. Запитайте по назві, SKU або параметрах (DN65, 20 bar і т.д.). Також розумію польську та англійську.' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs, open])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    const newMsgs = [...msgs, { role: 'user' as const, content: text }]
    setMsgs(newMsgs)
    setLoading(true)
    try {
      const r = await api.chat(text, newMsgs.slice(-6))
      setMsgs(m => [...m, { role: 'assistant', content: r.reply }])
    } catch {
      setMsgs(m => [...m, { role: 'assistant', content: 'Помилка з\'єднання. Спробуйте ще раз.' }])
    } finally {
      setLoading(false)
    }
  }

  const renderContent = (text: string) => {
    // Simple markdown link rendering
    return text.replace(
      /\[([^\]]+)\]\(\/product\/(\d+)\)/g,
      '<a href="/product/$2" style="color:var(--accent)">$1</a>'
    )
  }

  return (
    <>
      <div className={`chat-panel ${open ? 'open' : ''}`}>
        <div className="chat-panel-header">
          <span>💬 AI Асистент</span>
          <button onClick={() => setOpen(false)}
            style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,.6)', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>
        <div className="chat-messages">
          {msgs.map((m, i) => (
            <div key={i} className={`chat-msg ${m.role}`}
              dangerouslySetInnerHTML={{ __html: m.role === 'assistant' ? renderContent(m.content) : m.content }} />
          ))}
          {loading && (
            <div className="chat-msg assistant">
              <div style={{ display: 'flex', gap: 4 }}>
                {[0,1,2].map(i => (
                  <span key={i} style={{
                    width: 6, height: 6, background: 'var(--text3)', borderRadius: '50%',
                    animation: `bounce 1s ${i*0.2}s infinite`
                  }} />
                ))}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
        <div className="chat-input-row">
          <textarea
            className="chat-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Запитайте про товар..."
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          />
          <button className="chat-send" onClick={send} disabled={loading}>→</button>
        </div>
      </div>
      <button className="chat-fab" onClick={() => setOpen(!open)}>
        {open ? '✕' : '💬'}
      </button>
      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-4px); }
        }
      `}</style>
    </>
  )
}

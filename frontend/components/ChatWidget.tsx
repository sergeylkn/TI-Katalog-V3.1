'use client'
import { useState, useRef, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'

interface Product {
  id: number; title: string; sku: string; subtitle: string
  image_url: string; attributes: Record<string, string>; page_number?: number
}

interface Msg {
  role: 'user' | 'assistant'
  content: string
  products?: Product[]
  params?: Record<string, any>
}

const QUICK = [
  'Шланг для харчових продуктів',
  'Гідравлічний шланг 200 bar',
  'Camlock з\u2019єднання нержавійка',
  'Кульовий кран DN50',
  'Пневматичний шланг 8мм',
]

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([{
    role: 'assistant',
    content: `Привіт! Я Тарас, ваш технічний консультант TI-Katalog.\n\nОпишіть що вам потрібно — підберу з каталогу оптимальний варіант. Чим більше деталей — тим точніший підбір:\n• **Середовище** (вода, повітря, хімія, їжа, нафта...)\n• **Температура** і **тиск** (bar)\n• **Діаметр** (DN або мм)\n• **Матеріал** (гума, ПВХ, нержавіюча сталь...)\n\nПідтримую 🇺🇦 UA · 🇵🇱 PL · 🇬🇧 EN`,
  }])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const router = useRouter()
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || ''

  useEffect(() => {
    if (open) {
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    }
  }, [msgs, open])

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus()
  }, [open])

  const send = async (text?: string) => {
    const q = (text || input).trim()
    if (!q || loading) return
    setInput('')

    const userMsg: Msg = { role: 'user', content: q }
    const history = msgs.map(m => ({ role: m.role, content: m.content }))
    setMsgs(prev => [...prev, userMsg])
    setLoading(true)

    try {
      const r = await fetch(`${API_BASE}/api/chat/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: q, history: history.slice(-10) }),
      })
      const data = await r.json()
      setMsgs(prev => [...prev, {
        role: 'assistant',
        content: data.reply || 'Помилка відповіді',
        products: data.search_results || [],
        params: data.params_detected || {},
      }])
    } catch {
      setMsgs(prev => [...prev, { role: 'assistant', content: "❌ Помилка з'єднання. Спробуйте ще раз." }])
    } finally {
      setLoading(false)
    }
  }

  const openSearch = (q: string) => {
    router.push(`/search?q=${encodeURIComponent(q)}`)
    setOpen(false)
  }

  const lastUserQuery = () => {
    const userMsgs = msgs.filter(m => m.role === 'user')
    return userMsgs[userMsgs.length - 1]?.content || ''
  }

  // Render markdown-like text
  const renderContent = (text: string) => {
    return text
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code style="background:var(--bg2);padding:1px 5px;border-radius:3px;font-family:var(--font-mono);font-size:11px;">$1</code>')
      .replace(/\[([^\]]+)\]\(\/product\/(\d+)\)/g,
        '<a href="/product/$2" style="color:var(--accent);font-weight:600;text-decoration:underline;" target="_blank">$1 ↗</a>')
      .replace(/→/g, '<span style="color:var(--accent)">→</span>')
      .replace(/•/g, '<span style="color:var(--accent)">•</span>')
      .replace(/\n/g, '<br/>')
  }

  const panelW = expanded ? 520 : 360

  return (
    <>
      {/* ── Chat Panel ── */}
      <div style={{
        position: 'fixed', bottom: 88, right: 24, zIndex: 500,
        width: panelW, maxHeight: expanded ? '80vh' : 520,
        background: 'var(--card)', border: '1px solid var(--border2)',
        borderRadius: 'var(--radius2)', boxShadow: 'var(--shadow2)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        transform: open ? 'scale(1) translateY(0)' : 'scale(0.95) translateY(10px)',
        opacity: open ? 1 : 0, pointerEvents: open ? 'all' : 'none',
        transition: 'all 0.2s ease',
      }}>

        {/* Header */}
        <div style={{
          background: 'var(--nav-bg)', padding: '12px 16px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              background: 'var(--accent)', display: 'flex',
              alignItems: 'center', justifyContent: 'center', fontSize: 16,
            }}>🔧</div>
            <div>
              <div style={{ color: 'white', fontSize: 13, fontWeight: 600 }}>Тарас · AI Консультант</div>
              <div style={{ color: 'rgba(255,255,255,.45)', fontSize: 11 }}>TI-Katalog · Tubes International</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => setExpanded(!expanded)} style={{
              background: 'rgba(255,255,255,.08)', border: 'none', color: 'rgba(255,255,255,.6)',
              borderRadius: 5, padding: '4px 8px', cursor: 'pointer', fontSize: 13,
            }}>{expanded ? '⊟' : '⊞'}</button>
            <button onClick={() => setOpen(false)} style={{
              background: 'rgba(255,255,255,.08)', border: 'none', color: 'rgba(255,255,255,.6)',
              borderRadius: 5, padding: '4px 8px', cursor: 'pointer', fontSize: 16,
            }}>✕</button>
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 14px 8px', display: 'flex', flexDirection: 'column', gap: 12 }}>

          {msgs.map((m, i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start', gap: 8 }}>

              {/* Message bubble */}
              <div style={{
                maxWidth: '88%',
                background: m.role === 'user' ? 'var(--accent)' : 'var(--bg2)',
                color: m.role === 'user' ? 'white' : 'var(--text)',
                padding: '10px 14px', borderRadius: m.role === 'user' ? '14px 14px 2px 14px' : '14px 14px 14px 2px',
                fontSize: 13, lineHeight: 1.6,
              }} dangerouslySetInnerHTML={{ __html: renderContent(m.content) }} />

              {/* Detected params badge */}
              {m.role === 'assistant' && m.params && Object.keys(m.params).length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, maxWidth: '88%' }}>
                  {Object.entries(m.params).map(([k, v]) => (
                    <span key={k} style={{
                      fontSize: 10, background: 'var(--accent-bg)', color: 'var(--accent)',
                      padding: '2px 7px', borderRadius: 3, fontFamily: 'var(--font-mono)', fontWeight: 600,
                    }}>{k}={String(v)}</span>
                  ))}
                </div>
              )}

              {/* Product cards */}
              {m.role === 'assistant' && m.products && m.products.length > 0 && (
                <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ fontSize: 11, color: 'var(--text3)', padding: '0 4px' }}>
                    📦 Знайдено в каталозі: {m.products.length} товарів
                  </div>
                  {m.products.map(p => (
                    <a key={p.id} href={`/product/${p.id}`} target="_blank" style={{ textDecoration: 'none' }}>
                      <div style={{
                        display: 'flex', gap: 10, alignItems: 'center',
                        background: 'var(--card)', border: '1px solid var(--border)',
                        borderRadius: 8, padding: '8px 10px',
                        transition: 'border-color .15s, box-shadow .15s',
                        cursor: 'pointer',
                      }}
                        onMouseEnter={e => {
                          (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--accent)'
                          ;(e.currentTarget as HTMLDivElement).style.boxShadow = '0 2px 8px rgba(196,30,30,.15)'
                        }}
                        onMouseLeave={e => {
                          (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border)'
                          ;(e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
                        }}
                      >
                        {/* Thumbnail */}
                        <div style={{
                          width: 44, height: 44, flexShrink: 0,
                          background: 'var(--bg2)', borderRadius: 6,
                          overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>
                          {p.image_url ? (
                            <img src={`${API_BASE}${p.image_url}`} alt={p.title}
                              style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 4 }}
                              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                          ) : <span style={{ fontSize: 20 }}>📄</span>}
                        </div>

                        {/* Info */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {p.title}
                          </div>
                          {p.sku && (
                            <div style={{ fontSize: 10, color: 'var(--accent)', fontFamily: 'var(--font-mono)', marginTop: 1 }}>
                              {p.sku}
                            </div>
                          )}
                          {p.subtitle && (
                            <div style={{ fontSize: 10, color: 'var(--text2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1 }}>
                              {p.subtitle}
                            </div>
                          )}
                          {Object.keys(p.attributes || {}).length > 0 && (
                            <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>
                              {Object.entries(p.attributes).slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                            </div>
                          )}
                        </div>
                        <span style={{ color: 'var(--text3)', fontSize: 16, flexShrink: 0 }}>›</span>
                      </div>
                    </a>
                  ))}

                  {/* Show all in search */}
                  <button onClick={() => openSearch(lastUserQuery())} style={{
                    background: 'transparent', color: 'var(--accent)',
                    border: '1px solid var(--accent)', borderRadius: 7,
                    padding: '7px 12px', fontSize: 12, fontWeight: 600,
                    cursor: 'pointer', width: '100%', fontFamily: 'var(--font-sans)',
                    transition: 'background .15s',
                  }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--accent-bg)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    🔍 Переглянути всі результати в каталозі →
                  </button>
                </div>
              )}
            </div>
          ))}

          {/* Loading */}
          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                background: 'var(--bg2)', borderRadius: '14px 14px 14px 2px',
                padding: '10px 14px', display: 'flex', gap: 5, alignItems: 'center',
              }}>
                {[0,1,2].map(i => (
                  <span key={i} style={{
                    width: 7, height: 7, background: 'var(--accent)', borderRadius: '50%',
                    display: 'inline-block',
                    animation: `chatbounce .8s ${i*0.15}s infinite ease-in-out`,
                  }} />
                ))}
                <span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 4 }}>шукаю в каталозі...</span>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Quick suggestions (show only at start) */}
        {msgs.length <= 1 && !loading && (
          <div style={{ padding: '4px 14px 8px', display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {QUICK.map(q => (
              <button key={q} onClick={() => send(q)} style={{
                background: 'var(--bg2)', border: '1px solid var(--border)',
                borderRadius: 20, padding: '4px 10px', fontSize: 11, color: 'var(--text2)',
                cursor: 'pointer', fontFamily: 'var(--font-sans)',
                transition: 'background .15s, color .15s',
              }}
                onMouseEnter={e => { (e.currentTarget.style.background='var(--accent-bg)'); (e.currentTarget.style.color='var(--accent)') }}
                onMouseLeave={e => { (e.currentTarget.style.background='var(--bg2)'); (e.currentTarget.style.color='var(--text2)') }}
              >{q}</button>
            ))}
          </div>
        )}

        {/* Input */}
        <div style={{
          padding: '8px 12px 12px', borderTop: '1px solid var(--border)',
          display: 'flex', gap: 8, alignItems: 'flex-end', background: 'var(--card)',
        }}>
          <textarea ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Опишіть що потрібно підібрати..."
            rows={1}
            style={{
              flex: 1, border: '1px solid var(--border2)', borderRadius: 8,
              padding: '9px 12px', fontSize: 13, fontFamily: 'var(--font-sans)',
              background: 'var(--bg)', color: 'var(--text)', outline: 'none',
              resize: 'none', maxHeight: 100, overflowY: 'auto',
              lineHeight: 1.5,
            }}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
            }}
          />
          <button onClick={() => send()} disabled={loading || !input.trim()} style={{
            background: input.trim() && !loading ? 'var(--accent)' : 'var(--bg2)',
            color: input.trim() && !loading ? 'white' : 'var(--text3)',
            border: 'none', borderRadius: 8, padding: '9px 16px',
            cursor: input.trim() && !loading ? 'pointer' : 'default',
            fontSize: 16, transition: 'background .2s, color .2s', flexShrink: 0,
          }}>
            {loading ? '⏳' : '↑'}
          </button>
        </div>
      </div>

      {/* ── FAB ── */}
      <button onClick={() => setOpen(!open)} style={{
        position: 'fixed', bottom: 24, right: 24, zIndex: 500,
        width: 56, height: 56, borderRadius: '50%',
        background: open ? 'var(--nav-bg)' : 'var(--accent)',
        color: 'white', border: 'none', cursor: 'pointer',
        boxShadow: '0 4px 20px rgba(196,30,30,.4)',
        fontSize: open ? 20 : 24,
        transition: 'all .2s', display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
        onMouseEnter={e => (e.currentTarget.style.transform = 'scale(1.08)')}
        onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
        title={open ? 'Закрити' : 'AI Консультант'}
      >
        {open ? '✕' : '🔧'}
      </button>

      <style>{`
        @keyframes chatbounce {
          0%, 80%, 100% { transform: translateY(0) scale(1); opacity:.5 }
          40% { transform: translateY(-5px) scale(1.2); opacity:1 }
        }
      `}</style>
    </>
  )
}

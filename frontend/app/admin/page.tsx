'use client'
import { useEffect, useState, useRef } from 'react'
import Navbar from '@/components/Navbar'
import { api } from '@/lib/api'

export default function AdminPage() {
  const [apiKey, setApiKey] = useState('')
  const [openaiKey, setOpenaiKey] = useState('')
  const [status, setStatus] = useState<any>(null)
  const [logs, setLogs] = useState<any[]>([])
  const [parseLogs, setParseLogs] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const timer = useRef<any>(null)

  const refresh = async () => {
    try {
      const [s, l, pl] = await Promise.all([
        api.importStatus(), api.importLogs(50), api.parseLogs(50)
      ])
      setStatus(s)
      setLogs(l.logs || [])
      setParseLogs(pl.logs || [])
    } catch {}
  }

  useEffect(() => {
    refresh()
    timer.current = setInterval(refresh, 5000)
    return () => clearInterval(timer.current)
  }, [])

  const saveKey = async () => {
    try { await api.setApiKey(apiKey); setMsg('✅ Ключ збережено') }
    catch { setMsg('❌ Помилка') }
  }

  const doImport = async () => {
    try { await api.importAll(); setMsg('✅ Імпорт запущено'); refresh() }
    catch { setMsg('❌ Помилка') }
  }

  const doClear = async () => {
    if (!confirm('Очистити всю БД?')) return
    try { await api.clearDatabase(); setMsg('✅ БД очищена'); refresh() }
    catch { setMsg('❌ Помилка') }
  }

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>
        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 28, marginBottom: 24 }}>
          Адмін панель
        </h1>

        {msg && (
          <div style={{
            padding: '10px 16px', borderRadius: 'var(--radius)', marginBottom: 20,
            background: msg.startsWith('✅') ? '#EAF3DE' : '#FCEBEB',
            color: msg.startsWith('✅') ? '#3B6D11' : '#A32D2D', fontSize: 13
          }}>{msg}</div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 28 }}>
          {/* API Keys */}
          <div className="card">
            <h3 style={{ fontFamily: 'var(--font-serif)', marginBottom: 14 }}>🔑 API Ключі</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div>
                <label style={{ fontSize: 12, color: 'var(--text2)', display: 'block', marginBottom: 5 }}>
                  Anthropic API Key (для чату)
                </label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                    placeholder="sk-ant-..."
                    style={{
                      flex: 1, padding: '8px 12px', background: 'var(--bg2)',
                      border: '1px solid var(--border2)', borderRadius: 'var(--radius)',
                      color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 12
                    }}
                  />
                  <button className="btn btn-primary btn-sm" onClick={saveKey}>Зберегти</button>
                </div>
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--text2)', display: 'block', marginBottom: 5 }}>
                  OpenAI API Key (для embeddings/векторний пошук)
                </label>
                <input
                  type="password" value={openaiKey} onChange={e => setOpenaiKey(e.target.value)}
                  placeholder="sk-..."
                  style={{
                    width: '100%', padding: '8px 12px', background: 'var(--bg2)',
                    border: '1px solid var(--border2)', borderRadius: 'var(--radius)',
                    color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 12
                  }}
                />
                <p style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>
                  Додайте OPENAI_API_KEY в Railway змінні середовища
                </p>
              </div>
            </div>
          </div>

          {/* Status */}
          <div className="card">
            <h3 style={{ fontFamily: 'var(--font-serif)', marginBottom: 14 }}>📊 Статус імпорту</h3>
            {status ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  ['Всього документів', status.total],
                  ['Завершено', status.done],
                  ['В обробці', status.parsing],
                  ['Очікують', status.pending],
                  ['Помилок', status.error],
                  ['Товарів в БД', status.products],
                ].map(([label, val]) => (
                  <div key={String(label)} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span style={{ color: 'var(--text2)' }}>{label}</span>
                    <strong style={{ fontFamily: 'var(--font-mono)' }}>{val ?? '—'}</strong>
                  </div>
                ))}
                {status.total > 0 && (
                  <div style={{
                    height: 6, background: 'var(--bg2)', borderRadius: 3, marginTop: 6, overflow: 'hidden'
                  }}>
                    <div style={{
                      height: '100%', borderRadius: 3, background: 'var(--accent)',
                      width: `${Math.round((status.done / status.total) * 100)}%`,
                      transition: 'width .5s'
                    }} />
                  </div>
                )}
              </div>
            ) : (
              <div className="loader-wrap"><div className="spinner" /></div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="card" style={{ marginBottom: 28 }}>
          <h3 style={{ fontFamily: 'var(--font-serif)', marginBottom: 14 }}>⚙️ Дії</h3>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={doImport}>▶ Імпортувати всі PDF</button>
            <button className="btn btn-ghost" onClick={refresh}>↻ Оновити статус</button>
            <button
              className="btn btn-ghost"
              style={{ color: '#A32D2D', borderColor: '#A32D2D' }}
              onClick={doClear}
            >🗑 Очистити БД</button>
          </div>
          <p style={{ fontSize: 12, color: 'var(--text3)', marginTop: 10 }}>
            Після очистки БД запустіть "Імпортувати всі PDF". Час: ~15-20 хв. Вартість: $0.02 (embeddings).
          </p>
        </div>

        {/* Logs */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div className="card">
            <h3 style={{ fontFamily: 'var(--font-serif)', marginBottom: 12, fontSize: 18 }}>
              Лог імпорту
            </h3>
            <div style={{ maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {logs.slice().reverse().map((l: any, i: number) => (
                <div key={i} style={{
                  fontSize: 11, fontFamily: 'var(--font-mono)', padding: '4px 8px',
                  borderRadius: 4, background: l.status === 'error' ? '#FCEBEB' : 'var(--bg2)',
                  color: l.status === 'error' ? '#A32D2D' : 'var(--text2)',
                }}>
                  {l.doc?.slice(0, 45)} — {l.msg?.slice(0, 50)}
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <h3 style={{ fontFamily: 'var(--font-serif)', marginBottom: 12, fontSize: 18 }}>
              Лог парсингу
            </h3>
            <div style={{ maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {parseLogs.slice().reverse().map((l: any, i: number) => (
                <div key={i} style={{
                  fontSize: 11, fontFamily: 'var(--font-mono)', padding: '4px 8px',
                  borderRadius: 4, background: l.level === 'error' ? '#FCEBEB' : 'var(--bg2)',
                  color: l.level === 'error' ? '#A32D2D' : 'var(--text2)',
                }}>
                  {l.msg?.slice(0, 80)}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

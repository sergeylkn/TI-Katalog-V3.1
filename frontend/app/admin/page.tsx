'use client'
import { useEffect, useState, useRef, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || ''

const f = (url: string, opts?: RequestInit) => fetch(`${API}${url}`, opts).then(r => r.json())

// ── Status badge ──────────────────────────────────────────────────────────────
function Badge({ status }: { status: string }) {
  const map: Record<string, { bg: string; color: string; label: string }> = {
    done:    { bg: '#EAF3DE', color: '#3B6D11', label: '✓ done' },
    error:   { bg: '#FCEBEB', color: '#A32D2D', label: '✕ error' },
    parsing: { bg: '#FEF3CD', color: '#854F0B', label: '⚙ parsing' },
    pending: { bg: '#F0F0F0', color: '#555',    label: '· pending' },
    warn:    { bg: '#FEF3CD', color: '#854F0B', label: '⚠ warn' },
    info:    { bg: '#E6F1FB', color: '#185FA5', label: 'ℹ info' },
    started: { bg: '#E6F1FB', color: '#185FA5', label: '▶ started' },
  }
  const s = map[status?.toLowerCase()] || { bg: '#F0F0F0', color: '#555', label: status || '?' }
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 10,
      background: s.bg, color: s.color, flexShrink: 0, whiteSpace: 'nowrap',
    }}>{s.label}</span>
  )
}

// ── Log row ───────────────────────────────────────────────────────────────────
function LogRow({ log, type }: { log: any; type: 'import' | 'parse' }) {
  const isErr = log.status === 'error' || log.level === 'error'
  const isOk  = log.status === 'done'
  const time  = log.at ? new Date(log.at).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
  const doc   = log.doc || (log.doc_id ? `doc#${log.doc_id}` : '')
  const msg   = log.msg || log.message || ''
  const status = log.status || log.level || 'info'

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '52px 80px 1fr auto',
      gap: 8, alignItems: 'center',
      padding: '5px 10px',
      borderRadius: 5,
      background: isErr ? 'rgba(163,45,45,.07)' : isOk ? 'rgba(59,109,17,.04)' : 'transparent',
      borderLeft: `3px solid ${isErr ? '#A32D2D' : isOk ? '#3B6D11' : 'transparent'}`,
      fontSize: 12,
    }}>
      <span style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>{time}</span>
      <Badge status={status} />
      <div style={{ minWidth: 0 }}>
        {doc && <span style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)', fontSize: 10, marginRight: 6 }}>{doc.slice(0, 30)}</span>}
        <span style={{ color: isErr ? '#A32D2D' : 'var(--text)', wordBreak: 'break-word' }}>{msg}</span>
      </div>
      <span style={{ fontSize: 10, color: 'var(--text3)' }} />
    </div>
  )
}

// ── ENV Key card ──────────────────────────────────────────────────────────────
function EnvCard({ name, val }: { name: string; val: any }) {
  const icons: Record<string, string> = {
    ANTHROPIC_API_KEY: '🤖', OPENAI_API_KEY: '🔮',
    DATABASE_URL: '🗄️', PORT: '🔌',
  }
  const descs: Record<string, string> = {
    ANTHROPIC_API_KEY: 'AI чат та підбір',
    OPENAI_API_KEY: 'Векторний пошук',
    DATABASE_URL: 'PostgreSQL',
    PORT: 'Порт сервера',
  }
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px', borderRadius: 8,
      border: `1px solid ${val?.active ? 'rgba(59,109,17,.3)' : 'rgba(163,45,45,.3)'}`,
      background: val?.active ? 'rgba(59,109,17,.04)' : 'rgba(163,45,45,.04)',
    }}>
      <span style={{ fontSize: 22 }}>{icons[name] || '⚙️'}</span>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <code style={{ fontSize: 11, fontWeight: 700 }}>{name}</code>
          <Badge status={val?.active ? 'done' : 'error'} />
        </div>
        <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2 }}>
          {descs[name]}
          {val?.active && val?.preview && (
            <code style={{ marginLeft: 8, color: 'var(--text2)' }}>{val.preview}</code>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AdminPage() {
  const [status, setStatus]       = useState<any>(null)
  const [envStatus, setEnvStatus] = useState<any>(null)
  const [importLogs, setImportLogs] = useState<any[]>([])
  const [parseLogs, setParseLogs]   = useState<any[]>([])
  const [indexStats, setIndexStats] = useState<any>(null)
  const [toast, setToast]         = useState<{ msg: string; ok: boolean } | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [logFilter, setLogFilter] = useState<'all'|'error'|'done'>('all')
  const timerRef = useRef<any>(null)

  const notify = (msg: string, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 4000)
  }

  const refresh = useCallback(async () => {
    try {
      const [s, env, il, pl, idx] = await Promise.all([
        f('/api/admin/import-status'),
        f('/api/admin/env-status').catch(() => null),
        f('/api/admin/import-logs?limit=100'),
        f('/api/admin/parse-logs?limit=100'),
        f('/api/admin/index-stats').catch(() => null),
      ])
      setStatus(s)
      setEnvStatus(env)
      setImportLogs(il?.logs || [])
      setParseLogs(pl?.logs || [])
      setIndexStats(idx)
    } catch (e) {
      console.error(e)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = setInterval(refresh, 4000)
    } else {
      clearInterval(timerRef.current)
    }
    return () => clearInterval(timerRef.current)
  }, [autoRefresh, refresh])

  const doImport = async () => {
    try { await f('/api/admin/import-all-pdfs', { method: 'POST' }); notify('▶ Імпорт запущено'); refresh() }
    catch { notify('❌ Помилка запуску', false) }
  }

  const doClear = async () => {
    if (!confirm('Очистити ВСІ дані? Це незворотньо.')) return
    try { await f('/api/admin/clear-database', { method: 'POST' }); notify('✓ База очищена'); refresh() }
    catch { notify('❌ Помилка', false) }
  }

  const doRebuildIdx = async () => {
    try {
      await f('/api/admin/rebuild-indexes', { method: 'POST' })
      notify('▶ Перебудова індексів запущена (~2 хв)')
      setTimeout(refresh, 5000)
    } catch { notify('❌ Помилка', false) }
  }

  const progress = status?.total > 0 ? Math.round((status.done / status.total) * 100) : 0
  const isRunning = (status?.running || status?.parsing > 0)

  // Filter logs
  const filteredImport = importLogs.filter(l =>
    logFilter === 'all' ? true : logFilter === 'error' ? l.status === 'error' : l.status === 'done'
  )
  const filteredParse = parseLogs.filter(l =>
    logFilter === 'all' ? true : logFilter === 'error' ? l.level === 'error' : l.level === 'info'
  )

  return (
    <div style={{ fontFamily: 'var(--font-sans, system-ui)', minHeight: '100vh', background: 'var(--bg, #F5F4F0)', color: 'var(--text, #1a1a1a)' }}>
      {/* ── Header ── */}
      <div style={{ background: '#0E0E0E', padding: '14px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <a href="/" style={{ color: 'white', textDecoration: 'none', fontSize: 18, fontWeight: 700 }}>TI·Каталог</a>
          <span style={{ color: '#555' }}>›</span>
          <span style={{ color: '#aaa', fontSize: 14 }}>Адмін</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', color: '#aaa', fontSize: 12 }}>
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
            Авто-оновлення (4с)
          </label>
          <button onClick={refresh} style={{
            background: '#222', border: '1px solid #333', color: '#aaa',
            borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: 12,
          }}>↻ Оновити</button>
        </div>
      </div>

      {/* ── Toast ── */}
      {toast && (
        <div style={{
          position: 'fixed', top: 16, right: 16, zIndex: 999,
          padding: '10px 18px', borderRadius: 8,
          background: toast.ok ? '#EAF3DE' : '#FCEBEB',
          color: toast.ok ? '#3B6D11' : '#A32D2D',
          border: `1px solid ${toast.ok ? '#C0DD97' : '#F7C1C1'}`,
          fontSize: 13, fontWeight: 500, boxShadow: '0 4px 16px rgba(0,0,0,.1)',
        }}>{toast.msg}</div>
      )}

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 24px 60px' }}>

        {/* ── ENV STATUS ── */}
        <section style={{ marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            🔑 Змінні середовища
            {envStatus && (
              <Badge status={Object.values(envStatus).every((v: any) => v?.active) ? 'done' : 'error'} />
            )}
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {envStatus ? Object.entries(envStatus).map(([k, v]) => (
              <EnvCard key={k} name={k} val={v} />
            )) : (
              <div style={{ color: 'var(--text3)', fontSize: 13 }}>Завантаження...</div>
            )}
          </div>
          <div style={{
            marginTop: 10, padding: '8px 12px', background: 'rgba(196,30,30,.06)',
            borderRadius: 6, fontSize: 12, color: 'var(--text2)',
            borderLeft: '3px solid var(--accent, #C41E1E)',
          }}>
            💡 Ключі зберігаються в Railway → Variables і активні автоматично при кожному запуску.
          </div>
        </section>

        {/* ── IMPORT STATUS + ACTIONS ── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>

          {/* Status */}
          <section style={{ background: 'var(--card, white)', borderRadius: 12, padding: 20, border: '1px solid var(--border, #e8e5df)' }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              📊 Статус імпорту
              {isRunning && <span style={{ fontSize: 11, animation: 'pulse 1s infinite', color: '#854F0B' }}>⚙ виконується</span>}
            </h2>

            {status ? (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
                  {[
                    { label: 'Всього PDF', val: status.total, color: 'var(--text)' },
                    { label: 'Товарів в БД', val: status.products, color: '#185FA5' },
                    { label: '✓ Завершено', val: status.done, color: '#3B6D11' },
                    { label: '✕ Помилок', val: status.error, color: '#A32D2D' },
                    { label: '⚙ В обробці', val: status.parsing, color: '#854F0B' },
                    { label: '· Очікують', val: Math.max(0, status.total - status.done - status.parsing - status.error), color: '#555' },
                  ].map(({ label, val, color }) => (
                    <div key={label} style={{
                      padding: '10px 14px', borderRadius: 8,
                      background: 'var(--bg2, #F5F4F0)',
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                      <span style={{ fontSize: 12, color: 'var(--text2)' }}>{label}</span>
                      <strong style={{ fontSize: 20, fontFamily: 'var(--font-mono)', color }}>{val ?? 0}</strong>
                    </div>
                  ))}
                </div>

                {status.total > 0 && (
                  <>
                    <div style={{ height: 10, background: 'var(--bg2)', borderRadius: 5, overflow: 'hidden', marginBottom: 6 }}>
                      <div style={{
                        height: '100%', borderRadius: 5,
                        background: progress === 100 ? '#3B6D11' : '#C41E1E',
                        width: `${progress}%`, transition: 'width .5s',
                      }} />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text3)' }}>
                      <span>{progress}%</span>
                      <span>{status.done} / {status.total} документів</span>
                    </div>
                  </>
                )}

                {/* Index stats */}
                {indexStats && (
                  <div style={{ marginTop: 12, padding: '8px 12px', background: 'var(--bg2)', borderRadius: 6, fontSize: 12 }}>
                    🔍 Індекс артикулів: <strong>{indexStats.total_indexes?.toLocaleString() || 0}</strong> записів
                    {indexStats.by_type && Object.entries(indexStats.by_type).map(([k, v]: any) => (
                      <span key={k} style={{ marginLeft: 10, color: 'var(--text3)' }}>{k}: {v}</span>
                    ))}
                    {(!indexStats.total_indexes || indexStats.total_indexes === 0) && (
                      <span style={{ color: '#A32D2D', marginLeft: 8 }}>⚠ порожній — натисніть "Перебудувати"</span>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: 24, color: 'var(--text3)' }}>Завантаження...</div>
            )}
          </section>

          {/* Actions */}
          <section style={{ background: 'var(--card, white)', borderRadius: 12, padding: 20, border: '1px solid var(--border, #e8e5df)' }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>⚙️ Дії</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <button onClick={doImport} style={{
                padding: '12px 16px', borderRadius: 8, border: 'none',
                background: '#C41E1E', color: 'white', cursor: 'pointer',
                fontSize: 14, fontWeight: 600, textAlign: 'left',
              }}>
                ▶ Імпортувати всі PDF
                <div style={{ fontSize: 11, fontWeight: 400, opacity: .8, marginTop: 2 }}>
                  189 PDF · ~15-20 хв · ~$0.02 embeddings
                </div>
              </button>

              <button onClick={doRebuildIdx} style={{
                padding: '12px 16px', borderRadius: 8,
                border: '1px solid rgba(24,95,165,.4)',
                background: 'rgba(24,95,165,.05)', color: '#185FA5',
                cursor: 'pointer', fontSize: 13, fontWeight: 600, textAlign: 'left',
              }}>
                🔍 Перебудувати індекси артикулів
                <div style={{ fontSize: 11, fontWeight: 400, opacity: .8, marginTop: 2 }}>
                  ~1-2 хв · без реімпорту PDF · читає з БД
                </div>
              </button>

              <button onClick={refresh} style={{
                padding: '10px 16px', borderRadius: 8,
                border: '1px solid var(--border, #e8e5df)',
                background: 'transparent', color: 'var(--text)',
                cursor: 'pointer', fontSize: 13,
              }}>
                ↻ Оновити статус
              </button>

              <button onClick={doClear} style={{
                padding: '10px 16px', borderRadius: 8, marginTop: 8,
                border: '1px solid rgba(163,45,45,.3)',
                background: 'rgba(163,45,45,.04)', color: '#A32D2D',
                cursor: 'pointer', fontSize: 13,
              }}>
                🗑 Очистити БД (незворотньо)
              </button>
            </div>
          </section>
        </div>

        {/* ── LOGS ── */}
        <section style={{ background: 'var(--card, white)', borderRadius: 12, border: '1px solid var(--border, #e8e5df)', overflow: 'hidden' }}>

          {/* Log header + filter */}
          <div style={{
            padding: '14px 20px', borderBottom: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <h2 style={{ fontSize: 16, fontWeight: 700 }}>📋 Логи</h2>
              <span style={{ fontSize: 12, color: 'var(--text3)' }}>
                Імпорт: {importLogs.length} · Парсинг: {parseLogs.length}
              </span>
              {isRunning && (
                <span style={{ fontSize: 12, color: '#854F0B', background: '#FEF3CD', padding: '2px 8px', borderRadius: 4 }}>
                  ⚙ Оновлюється автоматично
                </span>
              )}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {(['all','error','done'] as const).map(f => (
                <button key={f} onClick={() => setLogFilter(f)} style={{
                  padding: '4px 12px', borderRadius: 20, fontSize: 12, cursor: 'pointer',
                  border: logFilter === f ? '1px solid var(--accent)' : '1px solid var(--border)',
                  background: logFilter === f ? 'var(--accent-bg, #fdf0f0)' : 'transparent',
                  color: logFilter === f ? 'var(--accent)' : 'var(--text2)',
                  fontWeight: logFilter === f ? 600 : 400,
                }}>
                  {f === 'all' ? 'Всі' : f === 'error' ? '✕ Помилки' : '✓ Успішні'}
                </button>
              ))}
            </div>
          </div>

          {/* Two columns */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', minHeight: 400 }}>

            {/* Import logs */}
            <div style={{ borderRight: '1px solid var(--border)' }}>
              <div style={{
                padding: '8px 14px', background: 'var(--bg2)',
                borderBottom: '1px solid var(--border)',
                fontSize: 12, fontWeight: 600, color: 'var(--text2)',
                display: 'flex', justifyContent: 'space-between',
              }}>
                <span>Лог імпорту документів</span>
                <span>{filteredImport.length} записів</span>
              </div>
              <div style={{ height: 500, overflowY: 'auto', padding: '4px 0' }}>
                {filteredImport.length === 0 ? (
                  <div style={{ padding: 24, textAlign: 'center', color: 'var(--text3)', fontSize: 13 }}>
                    {logFilter === 'all' ? 'Логів немає. Запустіть імпорт.' : `Немає записів "${logFilter}"`}
                  </div>
                ) : filteredImport.map((l, i) => (
                  <LogRow key={l.id || i} log={l} type="import" />
                ))}
              </div>
            </div>

            {/* Parse logs */}
            <div>
              <div style={{
                padding: '8px 14px', background: 'var(--bg2)',
                borderBottom: '1px solid var(--border)',
                fontSize: 12, fontWeight: 600, color: 'var(--text2)',
                display: 'flex', justifyContent: 'space-between',
              }}>
                <span>Лог парсингу PDF</span>
                <span>{filteredParse.length} записів</span>
              </div>
              <div style={{ height: 500, overflowY: 'auto', padding: '4px 0' }}>
                {filteredParse.length === 0 ? (
                  <div style={{ padding: 24, textAlign: 'center', color: 'var(--text3)', fontSize: 13 }}>
                    {logFilter === 'all' ? 'Логів немає.' : `Немає записів "${logFilter}"`}
                  </div>
                ) : filteredParse.map((l, i) => (
                  <LogRow key={l.id || i} log={l} type="parse" />
                ))}
              </div>
            </div>
          </div>

          {/* Live indicator */}
          <div style={{
            padding: '8px 20px', borderTop: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--text3)',
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: autoRefresh ? '#3B6D11' : '#aaa',
              display: 'inline-block',
              animation: autoRefresh && isRunning ? 'pulse 1s infinite' : 'none',
            }} />
            {autoRefresh ? (isRunning ? 'Живе оновлення — імпорт виконується' : 'Авто-оновлення активне') : 'Авто-оновлення вимкнено'}
          </div>
        </section>

      </div>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, sans-serif; }
        :root {
          --bg: #F5F4F0; --bg2: #EEECE7; --card: #FFFFFF;
          --text: #1a1a1a; --text2: #555; --text3: #888;
          --border: #E2DED8; --accent: #C41E1E;
          --font-mono: 'IBM Plex Mono', monospace;
          --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
        }
      `}</style>
    </div>
  )
}

'use client'
import { useEffect, useState, useRef, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || ''
const req = (url: string, opts?: RequestInit) => fetch(`${API}${url}`, opts).then(r => r.json())

// ── Types ─────────────────────────────────────────────────────────────────────
interface LogEntry { ts: string; level: string; msg: string; doc?: string; products?: number; pages?: number }
interface ProgressEvent { done: number; total: number; pct: number; current: string; products: number }
interface StatusData { total: number; done: number; error: number; parsing: number; products: number; running: boolean }

// ── Status card ───────────────────────────────────────────────────────────────
function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '10px 0' }}>
      <div style={{ fontSize: 28, fontWeight: 800, fontFamily: 'monospace', color: color || '#1a1a1a', lineHeight: 1 }}>
        {value ?? 0}
      </div>
      <div style={{ fontSize: 11, color: '#888', marginTop: 4 }}>{label}</div>
    </div>
  )
}

// ── Log line ──────────────────────────────────────────────────────────────────
function LogLine({ entry, idx }: { entry: LogEntry; idx: number }) {
  const colors: Record<string, string> = {
    done: '#22c55e', error: '#ef4444', info: '#60a5fa',
    warn: '#f59e0b', progress: '#a78bfa',
  }
  const color = colors[entry.level] || '#94a3b8'

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '52px 12px 1fr',
      gap: 8, padding: '2px 0',
      opacity: Math.max(0.4, 1 - idx * 0.02),
    }}>
      <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>{entry.ts}</span>
      <span style={{ color, fontSize: 14, lineHeight: 1.4 }}>●</span>
      <span style={{ fontSize: 12, color: '#e2e8f0', lineHeight: 1.5, wordBreak: 'break-all' }}>
        {entry.doc && <span style={{ color: '#94a3b8', marginRight: 6 }}>[{entry.doc.slice(0, 35)}]</span>}
        {entry.msg}
        {entry.products !== undefined && (
          <span style={{ marginLeft: 8, color: '#22c55e', fontSize: 11 }}>+{entry.products} товарів</span>
        )}
      </span>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function AdminPage() {
  const [status, setStatus] = useState<StatusData | null>(null)
  const [envStatus, setEnvStatus] = useState<any>(null)
  const [indexStats, setIndexStats] = useState<any>(null)
  const [liveLog, setLiveLog] = useState<LogEntry[]>([])
  const [progress, setProgress] = useState<ProgressEvent | null>(null)
  const [connected, setConnected] = useState(false)
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null)
  const [tab, setTab] = useState<'live' | 'history'>('live')
  const [historyLogs, setHistoryLogs] = useState<any[]>([])
  const [parseLogs, setParseLogs] = useState<any[]>([])

  const logEndRef = useRef<HTMLDivElement>(null)
  const sseRef = useRef<EventSource | null>(null)
  const statusTimer = useRef<any>(null)

  const notify = (msg: string, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 5000)
  }

  // SSE connection
  useEffect(() => {
    const connect = () => {
      if (sseRef.current) sseRef.current.close()
      const es = new EventSource(`${API}/api/admin/live-log`)
      sseRef.current = es

      es.onopen = () => setConnected(true)
      es.onerror = () => {
        setConnected(false)
        setTimeout(connect, 3000) // reconnect
      }
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'ping') return
          if (data.type === 'connected') { setConnected(true); return }

          if (data.type === 'progress') {
            setProgress(data as ProgressEvent)
            refreshStatus()
          } else if (data.type === 'log') {
            const entry: LogEntry = {
              ts: data.ts || new Date().toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
              level: data.level || 'info',
              msg: data.msg || '',
              doc: data.doc,
              products: data.products,
              pages: data.pages,
            }
            setLiveLog(prev => [entry, ...prev].slice(0, 300))
            if (data.level === 'done' || data.level === 'error') {
              refreshStatus()
            }
          }
        } catch {}
      }
    }
    connect()
    return () => { sseRef.current?.close(); clearInterval(statusTimer.current) }
  }, [])

  // Auto-scroll live log
  useEffect(() => {
    if (tab === 'live') logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveLog, tab])

  const refreshStatus = useCallback(async () => {
    try {
      const [s, env, idx] = await Promise.all([
        req('/api/admin/import-status'),
        req('/api/admin/env-status').catch(() => null),
        req('/api/admin/index-stats').catch(() => null),
      ])
      setStatus(s); setEnvStatus(env); setIndexStats(idx)
    } catch {}
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const [il, pl] = await Promise.all([
        req('/api/admin/import-logs?limit=150'),
        req('/api/admin/parse-logs?limit=150'),
      ])
      setHistoryLogs(il?.logs || [])
      setParseLogs(pl?.logs || [])
    } catch {}
  }, [])

  useEffect(() => {
    refreshStatus()
    statusTimer.current = setInterval(refreshStatus, 5000)
    return () => clearInterval(statusTimer.current)
  }, [refreshStatus])

  useEffect(() => {
    if (tab === 'history') loadHistory()
  }, [tab, loadHistory])

  const doImport = async () => {
    try {
      await req('/api/admin/import-all-pdfs', { method: 'POST' })
      notify('▶ Імпорт запущено — дивіться консоль нижче')
      setTab('live')
      setLiveLog([])
      setProgress(null)
    } catch { notify('❌ Помилка запуску', false) }
  }

  const doClear = async () => {
    if (!confirm('Очистити ВСІ дані? Незворотньо.')) return
    try { await req('/api/admin/clear-database', { method: 'POST' }); notify('✓ База очищена'); refreshStatus() }
    catch { notify('❌ Помилка', false) }
  }

  const doAction = async (url: string, msg: string) => {
    try {
      await req(url, { method: 'POST' })
      notify(msg); setTab('live')
      setTimeout(refreshStatus, 3000)
    } catch { notify('❌ Помилка', false) }
  }

  const progress_pct = progress?.pct ?? (status?.total ? Math.round(status.done / status.total * 100) : 0)
  const is_running = status?.running || (status?.parsing ?? 0) > 0 || (progress && progress.done < progress.total)

  return (
    <div style={{
      minHeight: '100vh', background: '#0f172a', color: '#e2e8f0',
      fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
    }}>

      {/* ── Header ── */}
      <div style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '12px 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <a href="/" style={{ color: '#f1f5f9', textDecoration: 'none', fontWeight: 700, fontSize: 18 }}>TI·Каталог</a>
          <span style={{ color: '#475569' }}>›</span>
          <span style={{ color: '#94a3b8', fontSize: 14 }}>Адміністрування</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: connected ? '#22c55e' : '#ef4444', display: 'inline-block', animation: connected && is_running ? 'pulse 1s infinite' : 'none' }} />
            <span style={{ color: '#94a3b8' }}>{connected ? (is_running ? 'Виконується...' : 'Підключено') : 'Відключено'}</span>
          </div>
          <button onClick={refreshStatus} style={{ background: '#334155', border: 'none', color: '#94a3b8', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: 12 }}>↻</button>
        </div>
      </div>

      {/* ── Toast ── */}
      {toast && (
        <div style={{ position: 'fixed', top: 16, right: 16, zIndex: 999, padding: '10px 18px', borderRadius: 8, background: toast.ok ? '#166534' : '#7f1d1d', color: 'white', fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,.4)' }}>
          {toast.msg}
        </div>
      )}

      <div style={{ maxWidth: 1300, margin: '0 auto', padding: '20px 20px 60px', display: 'flex', gap: 16 }}>

        {/* ── Left sidebar ── */}
        <div style={{ width: 280, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Status numbers */}
          <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: '16px 8px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1, padding: '0 12px', marginBottom: 12 }}>Статус імпорту</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: '#334155' }}>
              {[
                { label: 'Всього PDF', value: status?.total ?? 0, color: '#e2e8f0' },
                { label: 'Товарів в БД', value: status?.products ?? 0, color: '#60a5fa' },
                { label: '✓ Готово', value: status?.done ?? 0, color: '#22c55e' },
                { label: '✕ Помилки', value: status?.error ?? 0, color: '#ef4444' },
                { label: '⚙ Парситься', value: status?.parsing ?? 0, color: '#f59e0b' },
                { label: '· Очікує', value: Math.max(0, (status?.total ?? 0) - (status?.done ?? 0) - (status?.parsing ?? 0) - (status?.error ?? 0)), color: '#64748b' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ background: '#1e293b', padding: '10px 8px', textAlign: 'center' }}>
                  <div style={{ fontSize: 24, fontWeight: 800, fontFamily: 'monospace', color, lineHeight: 1 }}>{value}</div>
                  <div style={{ fontSize: 10, color: '#64748b', marginTop: 3 }}>{label}</div>
                </div>
              ))}
            </div>

            {/* Progress bar */}
            {(status?.total ?? 0) > 0 && (
              <div style={{ padding: '12px 12px 4px' }}>
                <div style={{ height: 6, background: '#0f172a', borderRadius: 3, overflow: 'hidden', marginBottom: 6 }}>
                  <div style={{ height: '100%', background: progress_pct === 100 ? '#22c55e' : '#3b82f6', width: `${progress_pct}%`, transition: 'width .5s', borderRadius: 3 }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#64748b' }}>
                  <span>{progress_pct}%</span>
                  <span>{status?.done}/{status?.total}</span>
                </div>
              </div>
            )}

            {/* Current doc */}
            {progress?.current && (
              <div style={{ margin: '8px 12px 4px', padding: '6px 10px', background: '#0f172a', borderRadius: 6, fontSize: 11, color: '#60a5fa', wordBreak: 'break-all' }}>
                ⚙ {progress.current}
              </div>
            )}
          </div>

          {/* ENV status */}
          <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Ключі Railway</div>
            {envStatus ? Object.entries(envStatus).map(([key, val]: any) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid #1e293b' }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: val?.active ? '#22c55e' : '#ef4444', flexShrink: 0 }} />
                <span style={{ fontSize: 11, fontFamily: 'monospace', color: val?.active ? '#e2e8f0' : '#64748b', flex: 1 }}>{key}</span>
                {val?.active && val?.preview && <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>{val.preview}</span>}
              </div>
            )) : <div style={{ fontSize: 12, color: '#475569' }}>...</div>}
          </div>

          {/* Index stats */}
          {indexStats && (
            <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Індекс артикулів</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#60a5fa', fontFamily: 'monospace' }}>{indexStats.total_indexes?.toLocaleString() || 0}</div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>записів в індексі</div>
              {(!indexStats.total_indexes || indexStats.total_indexes === 0) && (
                <div style={{ fontSize: 11, color: '#f59e0b', marginTop: 6 }}>⚠ Запустіть "Виправити пошук"</div>
              )}
            </div>
          )}

          {/* Actions */}
          <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Дії</div>

            <button onClick={doImport} style={{ padding: '10px 14px', borderRadius: 8, border: 'none', background: '#dc2626', color: 'white', cursor: 'pointer', fontSize: 13, fontWeight: 600, textAlign: 'left' }}>
              ▶ Імпортувати всі PDF
              <div style={{ fontSize: 10, fontWeight: 400, opacity: .75, marginTop: 2 }}>189 PDF · ~20 хв · ~$0.02</div>
            </button>

            <button onClick={() => doAction('/api/admin/rebuild-search-text', '▶ Виправлення пошуку запущено (~5 хв)')} style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid #b45309', background: 'rgba(180,83,9,.1)', color: '#fbbf24', cursor: 'pointer', fontSize: 12, fontWeight: 600, textAlign: 'left' }}>
              🛠 Виправити пошук по артикулах
              <div style={{ fontSize: 10, fontWeight: 400, opacity: .75, marginTop: 2 }}>Без реімпорту · ~5 хв</div>
            </button>

            <button onClick={() => doAction('/api/admin/rebuild-indexes', '▶ Перебудова індексів запущена')} style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid #1d4ed8', background: 'rgba(29,78,216,.1)', color: '#60a5fa', cursor: 'pointer', fontSize: 12, fontWeight: 600, textAlign: 'left' }}>
              🔍 Перебудувати індекси артикулів
              <div style={{ fontSize: 10, fontWeight: 400, opacity: .75, marginTop: 2 }}>Без реімпорту · ~2 хв</div>
            </button>

            <button onClick={() => refreshStatus()} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #334155', background: 'transparent', color: '#94a3b8', cursor: 'pointer', fontSize: 12 }}>
              ↻ Оновити статус
            </button>

            <button onClick={doClear} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #7f1d1d', background: 'rgba(127,29,29,.1)', color: '#f87171', cursor: 'pointer', fontSize: 12, marginTop: 4 }}>
              🗑 Очистити БД (незворотньо)
            </button>
          </div>
        </div>

        {/* ── Main console area ── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 0 }}>

          {/* Tabs */}
          <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid #334155' }}>
            {(['live', 'history'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} style={{
                padding: '10px 20px', border: 'none', borderBottom: `2px solid ${tab === t ? '#3b82f6' : 'transparent'}`,
                background: 'transparent', color: tab === t ? '#60a5fa' : '#64748b',
                cursor: 'pointer', fontSize: 13, fontWeight: tab === t ? 600 : 400,
                transition: 'color .15s',
              }}>
                {t === 'live' ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    {connected && is_running && <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', animation: 'pulse 1s infinite', display: 'inline-block' }} />}
                    🖥 Живий лог
                    {liveLog.length > 0 && <span style={{ fontSize: 11, background: '#1e3a5f', padding: '1px 6px', borderRadius: 10 }}>{liveLog.length}</span>}
                  </span>
                ) : '📋 Архів логів'}
              </button>
            ))}
          </div>

          {/* Live log console */}
          {tab === 'live' && (
            <div style={{
              flex: 1, background: '#020617', borderRadius: '0 0 12px 12px',
              border: '1px solid #1e293b', borderTop: 'none',
              padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column',
            }}>
              {/* Console header */}
              <div style={{ padding: '8px 16px', background: '#0f172a', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} />
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#22c55e', display: 'inline-block' }} />
                  <span style={{ fontSize: 11, color: '#475569', marginLeft: 8, fontFamily: 'monospace' }}>
                    ti-katalog — import console
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  {liveLog.length > 0 && (
                    <button onClick={() => setLiveLog([])} style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: 12 }}>
                      clear
                    </button>
                  )}
                  <span style={{ fontSize: 11, color: '#334155', fontFamily: 'monospace' }}>
                    {connected ? '● connected' : '○ disconnected'}
                  </span>
                </div>
              </div>

              {/* Log output */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', minHeight: 500, maxHeight: 'calc(100vh - 260px)', display: 'flex', flexDirection: 'column-reverse' }}>
                {liveLog.length === 0 ? (
                  <div style={{ color: '#334155', fontSize: 13, fontFamily: 'monospace', padding: '20px 0' }}>
                    <span style={{ color: '#22c55e' }}>$</span> Очікую на запуск імпорту...<br />
                    <span style={{ color: '#475569' }}>Натисніть "▶ Імпортувати всі PDF" щоб розпочати</span>
                  </div>
                ) : (
                  liveLog.map((entry, i) => (
                    <LogLine key={i} entry={entry} idx={i} />
                  ))
                )}
                <div ref={logEndRef} />
              </div>

              {/* Progress bar at bottom */}
              {progress && progress.total > 0 && (
                <div style={{ padding: '8px 16px', background: '#0f172a', borderTop: '1px solid #1e293b' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#64748b', marginBottom: 4 }}>
                    <span>{progress.current || 'Processing...'}</span>
                    <span>{progress.done}/{progress.total} ({progress.pct}%)</span>
                  </div>
                  <div style={{ height: 4, background: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ height: '100%', background: '#3b82f6', width: `${progress.pct}%`, transition: 'width .3s', borderRadius: 2 }} />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* History logs */}
          {tab === 'history' && (
            <div style={{ background: '#1e293b', borderRadius: '0 0 12px 12px', border: '1px solid #334155', borderTop: 'none', display: 'grid', gridTemplateColumns: '1fr 1fr', minHeight: 500 }}>
              {[
                { title: 'Лог імпорту документів', logs: historyLogs, getLevel: (l: any) => l.status, getMsg: (l: any) => l.msg || l.message || '', getDoc: (l: any) => l.doc || '' },
                { title: 'Лог парсингу PDF', logs: parseLogs, getLevel: (l: any) => l.level, getMsg: (l: any) => l.msg || l.message || '', getDoc: (l: any) => l.doc_id ? `doc#${l.doc_id}` : '' },
              ].map(({ title, logs, getLevel, getMsg, getDoc }) => (
                <div key={title} style={{ borderRight: '1px solid #334155' }}>
                  <div style={{ padding: '10px 14px', borderBottom: '1px solid #334155', fontSize: 12, fontWeight: 600, color: '#94a3b8', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{title}</span>
                    <span style={{ color: '#475569' }}>{logs.length}</span>
                  </div>
                  <div style={{ height: 540, overflowY: 'auto', padding: '4px 0' }}>
                    {logs.length === 0 ? (
                      <div style={{ padding: 24, textAlign: 'center', color: '#475569', fontSize: 12 }}>Порожньо</div>
                    ) : logs.map((l: any, i: number) => {
                      const colors: Record<string, string> = { done: '#22c55e', error: '#ef4444', info: '#60a5fa', queued: '#a78bfa', warn: '#f59e0b' }
                      const lv = getLevel(l)
                      const col = colors[lv] || '#64748b'
                      const ts = l.at ? new Date(l.at).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
                      return (
                        <div key={i} style={{ display: 'grid', gridTemplateColumns: '50px 8px 1fr', gap: 8, padding: '4px 14px', borderLeft: `2px solid ${lv === 'error' ? '#ef4444' : 'transparent'}` }}>
                          <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>{ts}</span>
                          <span style={{ color: col, fontSize: 12 }}>●</span>
                          <div style={{ fontSize: 12, color: lv === 'error' ? '#fca5a5' : '#94a3b8', wordBreak: 'break-all' }}>
                            {getDoc(l) && <span style={{ color: '#475569', marginRight: 6 }}>[{getDoc(l).slice(0,30)}]</span>}
                            {getMsg(l).slice(0, 120)}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
      `}</style>
    </div>
  )
}

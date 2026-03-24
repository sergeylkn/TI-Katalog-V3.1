'use client'
import { useEffect, useState, useRef, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || ''
const req = (url: string, opts?: RequestInit) =>
  fetch(`${API}${url}`, opts).then(r => r.json())

// ── Types ─────────────────────────────────────────────────────────────────────
interface LogEntry {
  ts: string
  level: string
  msg: string
  doc?: string
  products?: number
}
interface ProgressEvent { done: number; total: number; pct: number; current: string }
interface Status { total: number; done: number; error: number; parsing: number; pending: number; products: number; running: boolean }
interface IndexStats { total_products: number; total_indexes: number; with_description: number; with_certs: number }
interface EnvKey { active: boolean; preview: string }

// ── Helpers ───────────────────────────────────────────────────────────────────
function nowTs() {
  return new Date().toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function phaseIcon(msg: string) {
  if (/завантаж|download|fetching/i.test(msg)) return '⬇'
  if (/парс|parse|format [ABC]/i.test(msg)) return '🔍'
  if (/опис|description/i.test(msg)) return '📝'
  if (/сертиф|cert/i.test(msg)) return '🏷'
  if (/індекс|index/i.test(msg)) return '🗂'
  if (/пошук|search|rebuild/i.test(msg)) return '🔄'
  if (/✅|done|complete|готово/i.test(msg)) return '✅'
  if (/❌|error|помилк/i.test(msg)) return '❌'
  return '·'
}

// ── Log line ──────────────────────────────────────────────────────────────────
function LogLine({ entry }: { entry: LogEntry }) {
  const palette: Record<string, string> = {
    done: '#22c55e', error: '#f87171', info: '#60a5fa',
    warn: '#fbbf24', progress: '#a78bfa',
  }
  const col = palette[entry.level] || '#64748b'
  const icon = phaseIcon(entry.msg)

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '50px 18px 1fr',
      gap: '6px', padding: '3px 0', borderBottom: '1px solid #0f172a',
    }}>
      <span style={{ fontSize: 10, color: '#334155', fontFamily: 'monospace', paddingTop: 2 }}>{entry.ts}</span>
      <span style={{ fontSize: 13, lineHeight: '20px', textAlign: 'center' }}>{icon}</span>
      <span style={{ fontSize: 12, color: entry.level === 'error' ? '#fca5a5' : '#cbd5e1', lineHeight: '20px', wordBreak: 'break-all' }}>
        {entry.doc && (
          <span style={{ color: '#475569', marginRight: 6, fontFamily: 'monospace', fontSize: 11 }}>
            [{entry.doc.slice(0, 38)}]
          </span>
        )}
        <span style={{ color: col }}>{entry.msg}</span>
        {entry.products !== undefined && entry.products > 0 && (
          <span style={{ marginLeft: 8, color: '#22c55e', fontSize: 11, background: 'rgba(34,197,94,.1)', padding: '1px 6px', borderRadius: 4 }}>
            +{entry.products} товарів
          </span>
        )}
      </span>
    </div>
  )
}

// ── Stat pill ─────────────────────────────────────────────────────────────────
function Pill({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div style={{ background: '#0f172a', borderRadius: 8, padding: '10px 12px', textAlign: 'center' }}>
      <div style={{ fontSize: 22, fontWeight: 800, fontFamily: 'monospace', color, lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 10, color: '#475569', marginTop: 3, textTransform: 'uppercase', letterSpacing: .5 }}>{label}</div>
    </div>
  )
}

// ── History row ───────────────────────────────────────────────────────────────
function HistoryRow({ log }: { log: any }) {
  const statusColor: Record<string, string> = {
    completed: '#22c55e', failed: '#ef4444', pending: '#94a3b8', processing: '#f59e0b',
  }
  const col = statusColor[log.status] || '#64748b'
  const t = log.at ? new Date(log.at).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'
  const name = (log.doc || '').replace(/\.pdf$/i, '').slice(0, 55)

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '52px 10px 1fr 60px 60px',
      gap: 8, padding: '5px 14px', borderBottom: '1px solid #1e293b', alignItems: 'center',
    }}>
      <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>{t}</span>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: col, display: 'inline-block' }} />
      <span style={{ fontSize: 12, color: log.status === 'failed' ? '#fca5a5' : '#94a3b8', wordBreak: 'break-all' }}>
        {name}
        {log.error && <span style={{ color: '#ef4444', marginLeft: 8, fontSize: 10 }}>{log.error.slice(0, 60)}</span>}
      </span>
      <span style={{ fontSize: 11, color: '#64748b', textAlign: 'right' }}>
        {log.pages != null ? `${log.pages} стор.` : ''}
      </span>
      <span style={{ fontSize: 11, color: '#22c55e', textAlign: 'right', fontFamily: 'monospace' }}>
        {log.products > 0 ? `+${log.products}` : ''}
      </span>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function AdminPage() {
  const [status, setStatus] = useState<Status | null>(null)
  const [envStatus, setEnvStatus] = useState<Record<string, EnvKey> | null>(null)
  const [indexStats, setIndexStats] = useState<IndexStats | null>(null)
  const [liveLog, setLiveLog] = useState<LogEntry[]>([])
  const [progress, setProgress] = useState<ProgressEvent | null>(null)
  const [connected, setConnected] = useState(false)
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null)
  const [tab, setTab] = useState<'live' | 'history'>('live')
  const [historyLogs, setHistoryLogs] = useState<any[]>([])

  const logEndRef = useRef<HTMLDivElement>(null)
  const sseRef = useRef<EventSource | null>(null)
  const timerRef = useRef<any>(null)

  const notify = (msg: string, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 5000)
  }

  // ── SSE connection
  useEffect(() => {
    const connect = () => {
      sseRef.current?.close()
      const es = new EventSource(`${API}/api/admin/live-log`)
      sseRef.current = es
      es.onopen = () => setConnected(true)
      es.onerror = () => { setConnected(false); setTimeout(connect, 3000) }
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'ping' || data.type === 'connected') { setConnected(true); return }
          if (data.type === 'progress') {
            setProgress(data as ProgressEvent)
            refreshStatus()
          } else if (data.type === 'log') {
            const entry: LogEntry = {
              ts: data.ts || nowTs(),
              level: data.level || 'info',
              msg: data.msg || '',
              doc: data.doc,
              products: data.products,
            }
            setLiveLog(prev => [...prev, entry].slice(-400))
            if (data.level === 'done' || data.level === 'error') refreshStatus()
          }
        } catch {}
      }
    }
    connect()
    return () => { sseRef.current?.close(); clearInterval(timerRef.current) }
  }, [])

  // Auto-scroll to newest
  useEffect(() => {
    if (tab === 'live') logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveLog, tab])

  const refreshStatus = useCallback(async () => {
    try {
      const [s, env, idx] = await Promise.all([
        req('/api/admin/import-status').catch(() => null),
        req('/api/admin/env-status').catch(() => null),
        req('/api/admin/index-stats').catch(() => null),
      ])
      if (s) setStatus(s)
      if (env) setEnvStatus(env)
      if (idx) setIndexStats(idx)
    } catch {}
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const r = await req('/api/admin/import-logs?limit=200')
      setHistoryLogs(r?.logs || [])
    } catch {}
  }, [])

  useEffect(() => {
    refreshStatus()
    timerRef.current = setInterval(refreshStatus, 6000)
    return () => clearInterval(timerRef.current)
  }, [refreshStatus])

  useEffect(() => {
    if (tab === 'history') loadHistory()
  }, [tab, loadHistory])

  // ── Actions
  const doImport = async () => {
    try {
      await req('/api/admin/import-all-pdfs', { method: 'POST' })
      notify('▶ Імпорт запущено')
      setTab('live')
      setLiveLog([])
      setProgress(null)
    } catch { notify('❌ Помилка запуску', false) }
  }

  const doAction = async (url: string, msg: string) => {
    try {
      await req(url, { method: 'POST' })
      notify(msg)
      setTab('live')
      setTimeout(refreshStatus, 2000)
    } catch { notify('❌ Помилка', false) }
  }

  const doClear = async () => {
    if (!confirm('Очистити ВСІ дані? Незворотньо.')) return
    try {
      await req('/api/admin/clear-database', { method: 'POST' })
      notify('✓ База очищена')
      setStatus(null); setIndexStats(null)
      refreshStatus()
    } catch { notify('❌ Помилка', false) }
  }

  const pct = progress?.pct ?? (status?.total ? Math.round((status.done / status.total) * 100) : 0)
  const running = status?.running || ((status?.parsing ?? 0) > 0) || !!(progress && progress.done < progress.total)

  const total = indexStats?.total_products ?? 0
  const descPct = total > 0 ? Math.round((indexStats?.with_description ?? 0) / total * 100) : 0
  const certPct = total > 0 ? Math.round((indexStats?.with_certs ?? 0) / total * 100) : 0

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', fontFamily: "'IBM Plex Sans', system-ui, sans-serif" }}>

      {/* Header */}
      <div style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '12px 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <a href="/" style={{ color: '#f1f5f9', textDecoration: 'none', fontWeight: 700, fontSize: 17 }}>TI·Каталог</a>
          <span style={{ color: '#334155' }}>›</span>
          <span style={{ color: '#94a3b8', fontSize: 13 }}>Адміністрування</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#64748b' }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%', display: 'inline-block',
              background: connected ? '#22c55e' : '#ef4444',
              animation: connected && running ? 'pulse 1.2s infinite' : 'none',
            }} />
            {connected ? (running ? 'Виконується…' : 'Підключено') : 'Відключено'}
          </span>
          <button onClick={refreshStatus} style={{ background: '#1e293b', border: '1px solid #334155', color: '#64748b', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 12 }}>↻</button>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{ position: 'fixed', top: 16, right: 16, zIndex: 999, padding: '10px 18px', borderRadius: 8, background: toast.ok ? '#14532d' : '#7f1d1d', color: '#fff', fontSize: 13, fontWeight: 500, boxShadow: '0 4px 24px rgba(0,0,0,.5)' }}>
          {toast.msg}
        </div>
      )}

      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '20px 20px 60px', display: 'flex', gap: 14 }}>

        {/* ── Left sidebar ── */}
        <div style={{ width: 270, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* Import stats */}
          <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Статус імпорту</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              <Pill label="PDF файлів" value={status?.total ?? 0} color="#e2e8f0" />
              <Pill label="Товарів в БД" value={(status?.products ?? 0).toLocaleString()} color="#60a5fa" />
              <Pill label="Завершено" value={status?.done ?? 0} color="#22c55e" />
              <Pill label="Помилок" value={status?.error ?? 0} color={status?.error ? '#ef4444' : '#334155'} />
              <Pill label="Парситься" value={status?.parsing ?? 0} color="#f59e0b" />
              <Pill label="В черзі" value={status?.pending ?? 0} color="#64748b" />
            </div>

            {(status?.total ?? 0) > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ height: 5, background: '#0f172a', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', background: pct === 100 ? '#22c55e' : '#3b82f6', width: `${pct}%`, transition: 'width .4s', borderRadius: 3 }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#475569', marginTop: 4 }}>
                  <span>{pct}%</span>
                  <span>{status?.done}/{status?.total}</span>
                </div>
              </div>
            )}

            {progress?.current && (
              <div style={{ marginTop: 6, padding: '5px 8px', background: '#0f172a', borderRadius: 6, fontSize: 10, color: '#60a5fa', wordBreak: 'break-all', fontFamily: 'monospace' }}>
                ⚙ {progress.current}
              </div>
            )}
          </div>

          {/* Data quality */}
          <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Якість даних</div>
            {[
              { label: 'Індекс артикулів', value: (indexStats?.total_indexes ?? 0).toLocaleString(), color: '#818cf8' },
              { label: `Описи (${descPct}%)`, value: (indexStats?.with_description ?? 0).toLocaleString(), color: '#a78bfa' },
              { label: `Сертифікати (${certPct}%)`, value: (indexStats?.with_certs ?? 0).toLocaleString(), color: '#34d399' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #0f172a' }}>
                <span style={{ fontSize: 11, color: '#64748b' }}>{label}</span>
                <span style={{ fontSize: 14, fontWeight: 700, fontFamily: 'monospace', color }}>{value}</span>
              </div>
            ))}
          </div>

          {/* ENV keys */}
          <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Змінні середовища</div>
            {envStatus ? Object.entries(envStatus).map(([key, val]) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid #0f172a' }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: val?.active ? '#22c55e' : '#ef4444', flexShrink: 0 }} />
                <span style={{ fontSize: 10, fontFamily: 'monospace', color: val?.active ? '#94a3b8' : '#475569', flex: 1 }}>{key}</span>
                {val?.active && val?.preview && (
                  <span style={{ fontSize: 9, color: '#334155', fontFamily: 'monospace' }}>{val.preview}</span>
                )}
              </div>
            )) : <div style={{ fontSize: 11, color: '#334155' }}>Завантаження…</div>}
          </div>

          {/* Actions */}
          <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 14, display: 'flex', flexDirection: 'column', gap: 7 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Дії</div>

            <button
              onClick={doImport}
              disabled={!!running}
              style={{ padding: '10px 14px', borderRadius: 8, border: 'none', background: running ? '#374151' : '#dc2626', color: running ? '#6b7280' : '#fff', cursor: running ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: 600, textAlign: 'left' }}
            >
              ▶ Імпортувати всі PDF
              <div style={{ fontSize: 10, fontWeight: 400, opacity: .7, marginTop: 2 }}>189 PDF · перезаписує існуючі</div>
            </button>

            <button
              onClick={() => doAction('/api/admin/rebuild-search-text', '🔄 Переіндексацію пошуку запущено')}
              style={{ padding: '9px 14px', borderRadius: 8, border: '1px solid #92400e', background: 'rgba(146,64,14,.12)', color: '#fbbf24', cursor: 'pointer', fontSize: 12, fontWeight: 600, textAlign: 'left' }}
            >
              🔄 Переіндексувати пошук
              <div style={{ fontSize: 10, fontWeight: 400, opacity: .7, marginTop: 2 }}>Без реімпорту · ~3 хв</div>
            </button>

            <button
              onClick={() => doAction('/api/admin/rebuild-indexes', '🗂 Перебудову індексів запущено')}
              style={{ padding: '9px 14px', borderRadius: 8, border: '1px solid #1e3a8a', background: 'rgba(30,58,138,.12)', color: '#60a5fa', cursor: 'pointer', fontSize: 12, fontWeight: 600, textAlign: 'left' }}
            >
              🗂 Перебудувати індекси
              <div style={{ fontSize: 10, fontWeight: 400, opacity: .7, marginTop: 2 }}>Без реімпорту · ~2 хв</div>
            </button>

            <button
              onClick={refreshStatus}
              style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #334155', background: 'transparent', color: '#64748b', cursor: 'pointer', fontSize: 12 }}
            >
              ↻ Оновити статус
            </button>

            <button
              onClick={doClear}
              style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #7f1d1d', background: 'rgba(127,29,29,.1)', color: '#f87171', cursor: 'pointer', fontSize: 12, marginTop: 2 }}
            >
              🗑 Очистити БД (незворотньо)
            </button>
          </div>
        </div>

        {/* ── Console area ── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>

          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid #1e293b' }}>
            {(['live', 'history'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} style={{
                padding: '9px 20px', border: 'none',
                borderBottom: `2px solid ${tab === t ? '#3b82f6' : 'transparent'}`,
                background: 'transparent',
                color: tab === t ? '#60a5fa' : '#475569',
                cursor: 'pointer', fontSize: 13, fontWeight: tab === t ? 600 : 400,
              }}>
                {t === 'live' ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    {connected && running && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e', animation: 'pulse 1s infinite', display: 'inline-block' }} />}
                    🖥 Живий лог
                    {liveLog.length > 0 && <span style={{ fontSize: 10, background: '#1e3a5f', color: '#60a5fa', padding: '1px 6px', borderRadius: 10 }}>{liveLog.length}</span>}
                  </span>
                ) : (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    📋 Архів імпорту
                    {historyLogs.length > 0 && <span style={{ fontSize: 10, background: '#1e293b', color: '#64748b', padding: '1px 6px', borderRadius: 10 }}>{historyLogs.length}</span>}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Live console */}
          {tab === 'live' && (
            <div style={{ flex: 1, background: '#020617', borderRadius: '0 0 12px 12px', border: '1px solid #1e293b', borderTop: 'none', display: 'flex', flexDirection: 'column' }}>
              <div style={{ padding: '7px 14px', background: '#0a0f1e', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                  <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} />
                  <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
                  <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#22c55e', display: 'inline-block' }} />
                  <span style={{ fontSize: 11, color: '#334155', marginLeft: 8, fontFamily: 'monospace' }}>ti-katalog — import console</span>
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  {liveLog.length > 0 && (
                    <button onClick={() => setLiveLog([])} style={{ background: 'none', border: 'none', color: '#334155', cursor: 'pointer', fontSize: 11 }}>clear</button>
                  )}
                  <span style={{ fontSize: 11, color: connected ? '#1d4ed8' : '#334155', fontFamily: 'monospace' }}>
                    {connected ? '● connected' : '○ disconnected'}
                  </span>
                </div>
              </div>

              <div style={{ flex: 1, overflowY: 'auto', padding: '10px 14px', minHeight: 480, maxHeight: 'calc(100vh - 280px)' }}>
                {liveLog.length === 0 ? (
                  <div style={{ color: '#1e293b', fontSize: 13, fontFamily: 'monospace', padding: '24px 0', lineHeight: 2 }}>
                    <span style={{ color: '#22c55e' }}>$</span> Очікую на запуск…<br />
                    <span style={{ color: '#334155' }}>Натисніть "▶ Імпортувати всі PDF" або оберіть дію зліва</span>
                  </div>
                ) : liveLog.map((entry, i) => <LogLine key={i} entry={entry} />)}
                <div ref={logEndRef} />
              </div>

              {progress && progress.total > 0 && (
                <div style={{ padding: '8px 14px', background: '#0a0f1e', borderTop: '1px solid #1e293b' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#475569', marginBottom: 4 }}>
                    <span style={{ fontFamily: 'monospace', color: '#334155' }}>{progress.current || 'Processing…'}</span>
                    <span>{progress.done}/{progress.total} ({progress.pct}%)</span>
                  </div>
                  <div style={{ height: 3, background: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ height: '100%', background: '#3b82f6', width: `${progress.pct}%`, transition: 'width .3s' }} />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* History tab */}
          {tab === 'history' && (
            <div style={{ flex: 1, background: '#1e293b', borderRadius: '0 0 12px 12px', border: '1px solid #334155', borderTop: 'none', overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '52px 10px 1fr 60px 60px', gap: 8, padding: '8px 14px', background: '#0f172a', borderBottom: '1px solid #334155' }}>
                {['Час', '', 'Файл', 'Стор.', 'Товарів'].map((h, i) => (
                  <span key={i} style={{ fontSize: 10, color: '#475569', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .5 }}>{h}</span>
                ))}
              </div>
              <div style={{ height: 'calc(100vh - 260px)', overflowY: 'auto' }}>
                {historyLogs.length === 0 ? (
                  <div style={{ padding: 32, textAlign: 'center', color: '#334155', fontSize: 12 }}>
                    Немає даних · Запустіть імпорт
                  </div>
                ) : historyLogs.map((l, i) => <HistoryRow key={i} log={l} />)}
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.2} }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: #020617; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
        button:focus { outline: none; }
      `}</style>
    </div>
  )
}

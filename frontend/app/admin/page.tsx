'use client'
import { useEffect, useState, useRef } from 'react'
import Navbar from '@/components/Navbar'
import { api } from '@/lib/api'

const API = process.env.NEXT_PUBLIC_API_URL || ''

interface EnvVar {
  active: boolean
  source: string
  preview: string
}
interface EnvStatus {
  ANTHROPIC_API_KEY: EnvVar
  OPENAI_API_KEY: EnvVar
  DATABASE_URL: EnvVar
  PORT: EnvVar
}

const ENV_INFO: Record<string, { label: string; icon: string; desc: string }> = {
  ANTHROPIC_API_KEY: { label: 'Anthropic API Key', icon: '🤖', desc: 'AI чат та підбір товарів' },
  OPENAI_API_KEY:    { label: 'OpenAI API Key',    icon: '🔮', desc: 'Векторний пошук (embeddings)' },
  DATABASE_URL:      { label: 'Database URL',      icon: '🗄️', desc: 'PostgreSQL підключення' },
  PORT:              { label: 'Port',              icon: '🔌', desc: 'Порт сервера (8000)' },
}

export default function AdminPage() {
  const [envStatus, setEnvStatus] = useState<EnvStatus | null>(null)
  const [anthropicKey, setAnthropicKey] = useState('')
  const [status, setStatus] = useState<any>(null)
  const [logs, setLogs] = useState<any[]>([])
  const [parseLogs, setParseLogs] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const [msgType, setMsgType] = useState<'ok'|'err'>('ok')
  const timer = useRef<any>(null)

  const notify = (text: string, type: 'ok'|'err' = 'ok') => {
    setMsg(text); setMsgType(type)
    setTimeout(() => setMsg(''), 4000)
  }

  const refresh = async () => {
    try {
      const [s, l, pl, env] = await Promise.all([
        api.importStatus(), api.importLogs(60), api.parseLogs(60),
        fetch(`${API}/api/admin/env-status`).then(r => r.json()),
      ])
      setStatus(s)
      setLogs(l.logs || [])
      setParseLogs(pl.logs || [])
      setEnvStatus(env)
    } catch(e) {
      console.error(e)
    }
  }

  useEffect(() => {
    refresh()
    timer.current = setInterval(refresh, 5000)
    return () => clearInterval(timer.current)
  }, [])

  const saveKey = async () => {
    if (!anthropicKey.trim()) { notify('Введіть ключ', 'err'); return }
    try {
      await api.setApiKey(anthropicKey.trim())
      notify('✅ Ключ збережено (активний до рестарту сервера). Для постійного збереження — додайте в Railway Variables.')
      setAnthropicKey('')
      refresh()
    } catch { notify('❌ Помилка збереження', 'err') }
  }

  const doImport = async () => {
    try { await api.importAll(); notify('✅ Імпорт запущено'); refresh() }
    catch { notify('❌ Помилка запуску', 'err') }
  }

  const doClear = async () => {
    if (!confirm('Очистити ВСІ дані з бази? Це незворотньо.')) return
    try { await api.clearDatabase(); notify('✅ База очищена'); refresh() }
    catch { notify('❌ Помилка', 'err') }
  }

  const progress = status?.total > 0
    ? Math.round((status.done / status.total) * 100) : 0

  const allActive = envStatus
    ? Object.values(envStatus).every(v => v.active)
    : null

  return (
    <>
      <Navbar />
      <div className="container" style={{ paddingTop: 28, paddingBottom: 60 }}>

        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 28, marginBottom: 6 }}>
          Адмін панель
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 24 }}>
          TI-Katalog v5 · Tubes International
        </p>

        {/* Notification */}
        {msg && (
          <div style={{
            padding: '10px 16px', borderRadius: 'var(--radius)', marginBottom: 20,
            background: msgType === 'ok' ? '#EAF3DE' : '#FCEBEB',
            color: msgType === 'ok' ? '#3B6D11' : '#A32D2D',
            fontSize: 13, border: `1px solid ${msgType === 'ok' ? '#C0DD97' : '#F7C1C1'}`,
          }}>{msg}</div>
        )}

        {/* ── ENV STATUS PANEL ── */}
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: 20 }}>
              🔑 Статус змінних середовища
            </h2>
            {allActive !== null && (
              <span style={{
                fontSize: 12, fontWeight: 600, padding: '4px 12px', borderRadius: 20,
                background: allActive ? '#EAF3DE' : '#FCEBEB',
                color: allActive ? '#3B6D11' : '#A32D2D',
              }}>
                {allActive ? '✅ Всі активні' : '⚠️ Є проблеми'}
              </span>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {envStatus ? Object.entries(envStatus).map(([key, val]) => {
              const info = ENV_INFO[key] || { label: key, icon: '⚙️', desc: '' }
              return (
                <div key={key} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '12px 14px', borderRadius: 'var(--radius)',
                  border: `1px solid ${val.active ? 'rgba(63,153,11,.3)' : 'rgba(163,45,45,.3)'}`,
                  background: val.active ? 'rgba(63,153,11,.05)' : 'rgba(163,45,45,.05)',
                }}>
                  <span style={{ fontSize: 20 }}>{info.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                      <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text)' }}>
                        {key}
                      </span>
                      <span style={{
                        fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 10,
                        background: val.active ? '#EAF3DE' : '#FCEBEB',
                        color: val.active ? '#3B6D11' : '#A32D2D',
                      }}>
                        {val.active ? '● АКТИВНИЙ' : '○ ВІДСУТНІЙ'}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text3)' }}>
                      {info.desc}
                      {val.active && val.preview && (
                        <span style={{ marginLeft: 6, fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>
                          · {val.preview}
                        </span>
                      )}
                    </div>
                  </div>
                  <span style={{ fontSize: 18 }}>{val.active ? '✅' : '❌'}</span>
                </div>
              )
            }) : (
              <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: 20 }}>
                <div className="spinner" style={{ margin: '0 auto' }} />
              </div>
            )}
          </div>

          {/* Hint */}
          <div style={{
            marginTop: 14, padding: '10px 14px', borderRadius: 'var(--radius)',
            background: 'var(--bg2)', fontSize: 12, color: 'var(--text2)',
            borderLeft: '3px solid var(--accent)',
          }}>
            💡 Ключі зберігаються в Railway Variables і активуються автоматично при кожному запуску.
            Змінювати їх потрібно у Railway Dashboard → Variables.
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>

          {/* ── OVERRIDE KEY (temporary) ── */}
          <div className="card">
            <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: 18, marginBottom: 14 }}>
              🔄 Перезаписати ключ тимчасово
            </h3>
            <p style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 12, lineHeight: 1.6 }}>
              Активний до наступного рестарту сервера. Для постійної зміни — використовуйте Railway Variables.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontSize: 12, color: 'var(--text2)', fontWeight: 500 }}>
                Anthropic API Key
              </label>
              <input
                type="password"
                value={anthropicKey}
                onChange={e => setAnthropicKey(e.target.value)}
                placeholder="sk-ant-..."
                style={{
                  padding: '9px 12px', background: 'var(--bg2)',
                  border: '1px solid var(--border2)', borderRadius: 'var(--radius)',
                  color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 12,
                  outline: 'none',
                }}
                onKeyDown={e => e.key === 'Enter' && saveKey()}
              />
              <button className="btn btn-primary btn-sm" onClick={saveKey}
                style={{ alignSelf: 'flex-start' }}>
                Застосувати
              </button>
            </div>
          </div>

          {/* ── IMPORT STATUS ── */}
          <div className="card">
            <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: 18, marginBottom: 14 }}>
              📊 Статус імпорту
            </h3>
            {status ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  ['Всього документів', status.total, ''],
                  ['Завершено', status.done, '#3B6D11'],
                  ['В обробці', status.parsing, '#854F0B'],
                  ['Очікують', status.total - status.done - status.parsing - status.error, ''],
                  ['Помилок', status.error, '#A32D2D'],
                  ['Товарів в БД', status.products, '#185FA5'],
                ].map(([label, val, color]) => (
                  <div key={String(label)} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span style={{ color: 'var(--text2)' }}>{label}</span>
                    <strong style={{ fontFamily: 'var(--font-mono)', color: color as string || 'var(--text)' }}>
                      {val ?? 0}
                    </strong>
                  </div>
                ))}
                {status.total > 0 && (
                  <>
                    <div style={{ height: 8, background: 'var(--bg2)', borderRadius: 4, marginTop: 6, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', borderRadius: 4,
                        background: progress === 100 ? '#3B6D11' : 'var(--accent)',
                        width: `${progress}%`, transition: 'width .5s',
                      }} />
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text3)', textAlign: 'right' }}>
                      {progress}% · {status.running ? '⚙️ Виконується...' : (progress === 100 ? '✅ Завершено' : '⏸ Пауза')}
                    </div>
                  </>
                )}
              </div>
            ) : <div className="loader-wrap"><div className="spinner" /></div>}
          </div>
        </div>

        {/* ── ACTIONS ── */}
        <div className="card" style={{ marginBottom: 20 }}>
          <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: 18, marginBottom: 14 }}>⚙️ Дії</h3>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <button className="btn btn-primary" onClick={doImport}>
              ▶ Імпортувати всі PDF
            </button>
            <button className="btn btn-ghost" onClick={refresh}>
              ↻ Оновити статус
            </button>
            <button className="btn btn-ghost" style={{ color: '#A32D2D', borderColor: 'rgba(163,45,45,.4)' }}
              onClick={doClear}>
              🗑 Очистити БД
            </button>
          </div>
          <p style={{ fontSize: 12, color: 'var(--text3)', marginTop: 10 }}>
            Час імпорту: ~15-20 хв для 189 PDF · Вартість embeddings: ~$0.02
          </p>
        </div>

        {/* ── LOGS ── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          {[
            { title: 'Лог імпорту', items: logs, keyField: 'doc', msgField: 'msg', errField: 'status', errVal: 'error' },
            { title: 'Лог парсингу', items: parseLogs, keyField: 'doc_id', msgField: 'msg', errField: 'level', errVal: 'error' },
          ].map(({ title, items, msgField, errField, errVal }) => (
            <div key={title} className="card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: 18 }}>{title}</h3>
                <span style={{ fontSize: 11, color: 'var(--text3)' }}>{items.length} записів</span>
              </div>
              <div style={{ maxHeight: 280, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
                {items.length === 0 ? (
                  <p style={{ fontSize: 12, color: 'var(--text3)', textAlign: 'center', padding: '20px 0' }}>
                    Логів немає
                  </p>
                ) : items.slice().reverse().map((l: any, i: number) => (
                  <div key={i} style={{
                    fontSize: 11, fontFamily: 'var(--font-mono)',
                    padding: '4px 8px', borderRadius: 4,
                    background: l[errField] === errVal ? 'rgba(163,45,45,.08)' : 'var(--bg2)',
                    color: l[errField] === errVal ? '#A32D2D' : 'var(--text2)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }} title={(l[msgField] || '')}>
                    {l[msgField]?.slice(0, 90) || '—'}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

      </div>
    </>
  )
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Json = Record<string, any>
type Run = { ts?: string; verdict?: string; p0?: number; p1?: number; duration_s?: number; budget_usd?: number; budget_limit?: number; refs_verified?: number; refs_total?: number; pdf_pages?: number; z3_passed?: number; z3_total?: number; lean_ok?: boolean | null }

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(path, { cache: 'no-store', ...init })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}
const n = (value: unknown, fallback = '—') => value === null || value === undefined || value === '' ? fallback : String(value)
const date = (value?: string) => value ? new Date(value).toLocaleString('tr-TR') : 'henüz çalıştırılmadı'

function Badge({ label, state = 'neutral' }: { label: string; state?: 'ok' | 'fail' | 'warn' | 'neutral' }) {
  return <span className={`badge ${state}`}>{label}</span>
}
function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <article className="metric"><small>{label}</small><strong>{value}</strong>{detail && <em>{detail}</em>}</article>
}
function App() {
  const [latest, setLatest] = useState<Json | null>(null)
  const [history, setHistory] = useState<Run[]>([])
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [theme, setTheme] = useState(() => localStorage.getItem('dashboard-theme') || 'dark')
  const [selected, setSelected] = useState<Run | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [current, rows] = await Promise.all([api<Json>('/api/latest'), api<Run[]>('/api/run-history')])
      setLatest(current); setHistory(rows); setError('')
    } catch (e) { setError(e instanceof Error ? e.message : 'API bağlantısı kurulamadı') }
  }, [])
  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 15000); return () => window.clearInterval(timer) }, [refresh])
  useEffect(() => {
    document.documentElement.dataset.theme = theme; localStorage.setItem('dashboard-theme', theme)
    const source = new EventSource('/api/run')
    source.onopen = () => setConnected(true)
    source.onmessage = event => { try { setLatest(JSON.parse(event.data)); setConnected(true); refresh() } catch { /* keep last snapshot */ } }
    source.onerror = () => setConnected(false)
    return () => source.close()
  }, [theme, refresh])

  const run = async () => {
    setLoading(true); setError('')
    try { await api('/api/run-now', { method: 'POST', headers: { 'Content-Type': 'application/json' } }); await refresh() }
    catch (e) { setError(e instanceof Error ? e.message : 'Çalıştırma başarısız') }
    finally { setLoading(false) }
  }
  const stop = async () => {
    try { await api('/api/stop', { method: 'POST' }); setConnected(false) }
    catch (e) { setError(e instanceof Error ? e.message : 'Sunucu durdurulamadı') }
  }
  const verdict = latest?.verdict || 'UNKNOWN'
  const status = verdict === 'PASS' ? 'ok' : verdict === 'FAIL' || verdict === 'ERROR' ? 'fail' : 'warn'
  const p0 = latest?.p0 ?? latest?.findings?.p0
  const p1 = latest?.p1 ?? latest?.findings?.p1
  const budget = latest?.budget || {}
  const refs = latest?.refs || latest?.reference_verification || {}
  const kLayers = latest?.k_layers || latest?.klayers || latest?.status_board?.k_layers
  const layerList = useMemo(() => Array.isArray(kLayers) ? kLayers : [], [kLayers])

  return <div className="app">
    <header className="topbar"><div><p className="eyebrow">FREEBUFF · TESLİM KAPISI</p><h1>Stoic–Hume V5</h1><p className="subtitle">Kanıt zinciri ve yeniden üretilebilirlik panosu</p></div><div className="actions"><span className={`live ${connected ? 'online' : ''}`}>● {connected ? 'canlı' : 'bağlantı bekleniyor'}</span><button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} className="ghost">{theme === 'dark' ? '☼ Açık tema' : '☾ Koyu tema'}</button><button onClick={run} disabled={loading}>{loading ? 'Çalışıyor…' : 'Şimdi doğrula'}</button><button onClick={stop} className="danger ghost">Sunucuyu durdur</button></div></header>
    <main>
      {error && <div className="notice fail">{error}</div>}
      <section className="hero card"><div><span className="eyebrow">SON DOĞRULAMA</span><div className="verdict"><span className={`verdict-dot ${status}`} />{verdict}</div><p className="muted">{date(latest?.ts)}</p></div><div className="badges"><Badge label={`P0 ${n(p0, '0')}`} state={p0 ? 'fail' : 'ok'} /><Badge label={`P1 ${n(p1, '0')}`} state={p1 ? 'warn' : 'ok'} /><Badge label={`K8 Z3 ${n(latest?.z3_passed, '?')}/${n(latest?.z3_total, '?')}`} state="neutral" /><Badge label={`K9 Lean ${latest?.lean_ok === true ? 'PASS' : latest?.lean_ok === false ? 'FAIL' : '?'}`} state={latest?.lean_ok === false ? 'fail' : latest?.lean_ok === true ? 'ok' : 'neutral'} /></div></section>
      <section className="metrics"><Metric label="Çalışma süresi" value={latest?.duration_s != null ? `${latest.duration_s.toFixed?.(1) ?? latest.duration_s}s` : '—'} detail="verify_delivery --full" /><Metric label="Evrensel bütçe" value={budget.usd != null ? `$${Number(budget.usd).toFixed(2)}` : latest?.budget_usd != null ? `$${Number(latest.budget_usd).toFixed(2)}` : '—'} detail={budget.limit ? `limit $${budget.limit}` : 'limit bilinmiyor'} /><Metric label="Referans kapsamı" value={`${n(refs.verified ?? latest?.refs_verified)}/${n(refs.total ?? latest?.refs_total)}`} detail="doğrulanmış / toplam" /><Metric label="PDF sayfa" value={n(latest?.pdf_pages)} detail="beklenen 33" /></section>
      <section className="grid two"><article className="card"><div className="section-head"><h2>K-katman durumu</h2><span className="muted">fail-closed</span></div><div className="layers">{layerList.length ? layerList.map((layer: any, i: number) => <Badge key={i} label={`${layer.id || `K${i + 1}`} ${layer.verdict || layer.status || '?'}`} state={(layer.verdict || layer.status) === 'PASS' ? 'ok' : (layer.verdict || layer.status) === 'FAIL' ? 'fail' : 'neutral'} />) : <p className="muted">Katman özeti son snapshot içinde yok.</p>}</div></article><article className="card"><div className="section-head"><h2>Durum tahtası</h2><span className="muted">{latest?.status_board?.ts ? date(latest.status_board.ts) : ''}</span></div><p className={`board ${status}`}>{latest?.status_board?.message || latest?.status_board?.verdict || verdict}</p><p className="muted">Yerel geçiş ile temiz kopya/CI kanıtı ayrı tutulur.</p></article></section>
      <section className="card"><div className="section-head"><h2>Son doğrulama çalışmaları</h2><span className="muted">{history.length} kayıt</span></div><div className="table-wrap"><table><thead><tr><th>Zaman</th><th>Verdict</th><th>P0/P1</th><th>Süre</th><th>Bütçe</th><th>PDF</th></tr></thead><tbody>{history.length ? history.slice().reverse().map((item, i) => <tr key={item.ts || i} onClick={() => setSelected(item)}><td>{date(item.ts)}</td><td><Badge label={n(item.verdict)} state={item.verdict === 'PASS' ? 'ok' : item.verdict === 'FAIL' ? 'fail' : 'neutral'} /></td><td>{n(item.p0, '0')} / {n(item.p1, '0')}</td><td>{item.duration_s != null ? `${item.duration_s}s` : '—'}</td><td>{item.budget_usd != null ? `$${item.budget_usd}` : '—'}</td><td>{n(item.pdf_pages)}</td></tr>) : <tr><td colSpan={6} className="muted">Henüz çalıştırma kaydı yok.</td></tr>}</tbody></table></div></section>
      {selected && <section className="card detail"><div className="section-head"><h2>Çalışma ayrıntısı</h2><button className="ghost" onClick={() => setSelected(null)}>Kapat</button></div><pre>{JSON.stringify(selected, null, 2)}</pre></section>}
    </main><footer>Fail-closed doğrulama · API: /api/latest · SSE: /api/run · {latest?.commit_sha ? `SHA ${latest.commit_sha}` : 'SHA bekleniyor'}</footer>
  </div>
}
createRoot(document.getElementById('root')!).render(<App />)

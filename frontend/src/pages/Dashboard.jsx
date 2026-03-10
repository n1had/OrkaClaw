import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'

export default function Dashboard({ user }) {
  const navigate = useNavigate()

  const [runs, setRuns] = useState(null)        // null = loading, [] = empty
  const [histError, setHistError] = useState('')
  const [selected, setSelected] = useState(null) // full run object for modal
  const [loadingRun, setLoadingRun] = useState(false)

  useEffect(() => {
    fetch('/history', { credentials: 'include' })
      .then((r) => r.json())
      .then(setRuns)
      .catch(() => setHistError('Nije moguće učitati historiju.'))
  }, [])

  async function openRun(id) {
    setLoadingRun(true)
    try {
      const r = await fetch(`/history/${id}`, { credentials: 'include' })
      if (!r.ok) throw new Error()
      setSelected(await r.json())
    } catch {
      setHistError('Nije moguće učitati pokret.')
    } finally {
      setLoadingRun(false)
    }
  }

  function downloadRun(run) {
    const blob = new Blob([run.output_markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${run.stream}_${run.faza}_${run.id}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  function formatDate(iso) {
    const d = new Date(iso)
    const pad = (n) => String(n).padStart(2, '0')
    return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }

  // Show first non-empty input value as a short label for the run row
  function runLabel(run) {
    const first = String(Object.values(run.inputs || {}).find(Boolean) || '')
    return first.length > 60 ? first.slice(0, 60) + '…' : first
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-brand">
          Orka <span>/ Agenti</span>
        </div>
        <div className="topbar-right">
          <span className="user-badge">{user.name}</span>
          <a href="/auth/logout" className="btn btn-ghost" style={{ padding: '5px 12px', fontSize: 13 }}>
            Odjavi se
          </a>
        </div>
      </header>

      <div className="dashboard-body">
        <div className="dashboard-hero">
          <h1>Dobrodošao, {user.name.split(' ')[0]}</h1>
          <button className="btn btn-primary" onClick={() => navigate('/run')}>
            + Pokreni agenta
          </button>
        </div>

        <div className="section-card">
          <h2>Nedavni pokreti</h2>

          {histError && (
            <div className="error-box" style={{ marginBottom: 12 }}>{histError}</div>
          )}

          {runs === null && !histError && (
            <div className="empty-state">
              <div className="spinner" style={{ width: 20, height: 20, borderWidth: 2, margin: '0 auto' }} />
            </div>
          )}

          {runs !== null && runs.length === 0 && (
            <div className="empty-state">Još nema pokreta. Pokreni svog prvog agenta!</div>
          )}

          {runs !== null && runs.length > 0 && (
            <div className="run-list">
              {runs.map((r) => (
                <button
                  key={r.id}
                  className="run-row"
                  onClick={() => openRun(r.id)}
                  disabled={loadingRun}
                >
                  <div className="run-row-main">
                    <span className="run-row-agent">{r.agent_name}</span>
                    {runLabel(r) && <span className="run-row-label">{runLabel(r)}</span>}
                  </div>
                  <span className="run-row-date">{formatDate(r.created_at)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── History modal ── */}
      {selected && (
        <div className="history-overlay" onClick={() => setSelected(null)}>
          <div className="history-modal" onClick={(e) => e.stopPropagation()}>
            <div className="history-modal-header">
              <div>
                <div className="history-modal-title">{selected.agent_name}</div>
                <div className="history-modal-meta">{formatDate(selected.created_at)}</div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                <button className="btn btn-ghost" onClick={() => downloadRun(selected)}>
                  ↓ Preuzmi MD
                </button>
                <button className="btn btn-ghost" onClick={() => setSelected(null)}>
                  ✕
                </button>
              </div>
            </div>
            <div className="output-viewer">
              <ReactMarkdown>{selected.output_markdown}</ReactMarkdown>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

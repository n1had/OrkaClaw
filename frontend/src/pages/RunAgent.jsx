import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AgentSelector from '../components/AgentSelector'
import InputForm from '../components/InputForm'
import OutputViewer from '../components/OutputViewer'

const DEFAULT_MODEL = 'claude-sonnet-4-6'

const MODEL_GROUPS = [
  {
    group: 'Anthropic',
    models: [
      { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
      { value: 'claude-opus-4-6', label: 'Claude Opus 4.6' },
      { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' },
    ],
  },
  {
    group: 'OpenAI',
    models: [
      { value: 'gpt-4o', label: 'GPT-4o' },
      { value: 'gpt-4o-mini', label: 'GPT-4o mini' },
      { value: 'o3', label: 'o3' },
      { value: 'o4-mini', label: 'o4-mini' },
    ],
  },
  {
    group: 'Google',
    models: [
      { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
      { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
    ],
  },
]

export default function RunAgent({ user }) {
  const navigate = useNavigate()

  // Registry
  const [registry, setRegistry] = useState(null)

  // Selection
  const [selectedStream, setSelectedStream] = useState('')
  const [selectedFaza, setSelectedFaza] = useState('')
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL)

  // Inputs
  const [inputs, setInputs] = useState({})

  // Output
  const [output, setOutput] = useState('')
  const [running, setRunning] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  const readerRef = useRef(null)

  // Fetch registry on mount
  useEffect(() => {
    fetch('/registry', { credentials: 'include' })
      .then((r) => r.json())
      .then(setRegistry)
      .catch(() => setError('Nije moguće učitati registar agenata.'))
  }, [])

  // Reset inputs and model when agent changes
  useEffect(() => {
    setInputs({})
    setSelectedModel(registry?.[selectedStream]?.[selectedFaza]?.model ?? DEFAULT_MODEL)
  }, [selectedStream, selectedFaza])

  const agentConfig =
    registry && selectedStream && selectedFaza
      ? registry[selectedStream]?.[selectedFaza]
      : null

  // Validate required inputs
  function missingRequired() {
    if (!agentConfig) return true
    return agentConfig.inputs.some(
      (f) => f.required && !inputs[f.name]?.trim()
    )
  }

  async function handleRun() {
    if (missingRequired()) return
    setOutput('')
    setDone(false)
    setError('')
    setRunning(true)

    try {
      const response = await fetch(`/run/${selectedStream}/${selectedFaza}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ ...inputs, model: selectedModel }),
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        setError(err.detail || `Greška ${response.status}`)
        setRunning(false)
        return
      }

      const reader = response.body.getReader()
      readerRef.current = reader
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done: streamDone, value } = await reader.read()
        if (streamDone) break

        buffer += decoder.decode(value, { stream: true })

        // Process all complete SSE lines from the buffer
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep any incomplete trailing line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') {
            setDone(true)
            continue
          }
          try {
            const chunk = JSON.parse(data)
            if (typeof chunk === 'string') {
              setOutput((prev) => prev + chunk)
            } else if (chunk?.error) {
              setError(chunk.error)
            }
          } catch {
            // ignore malformed chunks
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  function handleDownload() {
    const filename = agentConfig?.output_file || 'output.md'
    const blob = new Blob([output], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  function handleStop() {
    readerRef.current?.cancel()
    setRunning(false)
  }

  const canRun = agentConfig && !running && !missingRequired()

  return (
    <div className="shell">
      <header className="topbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn-back" onClick={() => navigate('/dashboard')}>
            ← Nazad
          </button>
          <div className="topbar-brand">
            Orka <span>/ Pokreni agenta</span>
          </div>
        </div>
        <div className="topbar-right">
          <span className="user-badge">{user.name}</span>
          <a href="/auth/logout" className="btn btn-ghost" style={{ padding: '5px 12px', fontSize: 13 }}>
            Odjavi se
          </a>
        </div>
      </header>

      <div className="run-body">
        {/* ── Left panel: selector + form ── */}
        <div className="run-panel">
          <div className="run-panel-inner">
            <div>
              <div className="section-label">Agent</div>
              <AgentSelector
                registry={registry}
                selectedStream={selectedStream}
                selectedFaza={selectedFaza}
                onStreamChange={(s) => {
                  setSelectedStream(s)
                  setSelectedFaza('')
                }}
                onFazaChange={setSelectedFaza}
              />
            </div>

            {agentConfig && (
              <div>
                <div className="section-label">Model</div>
                <select
                  className="input-field"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                >
                  {MODEL_GROUPS.map(({ group, models }) => (
                    <optgroup key={group} label={group}>
                      {models.map((m) => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>
            )}

            {agentConfig && (
              <div>
                <div className="section-label">Unos</div>
                <InputForm
                  fields={agentConfig.inputs}
                  values={inputs}
                  onChange={setInputs}
                />
              </div>
            )}

            {agentConfig && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  className="btn btn-primary btn-run"
                  onClick={handleRun}
                  disabled={!canRun}
                >
                  {running ? 'Pokrenuto…' : 'Pokreni'}
                </button>
                {running && (
                  <button
                    className="btn btn-ghost"
                    onClick={handleStop}
                    style={{ flexShrink: 0 }}
                  >
                    Stop
                  </button>
                )}
              </div>
            )}

            {error && <div className="error-box">{error}</div>}
          </div>
        </div>

        {/* ── Right panel: output ── */}
        <div className="output-panel">
          {output || running ? (
            <>
              <div className="output-toolbar">
                <h2>
                  {running ? (
                    <>
                      <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2, display: 'inline-block', verticalAlign: 'middle', marginRight: 6 }} />
                      Agent radi…
                    </>
                  ) : (
                    'Output'
                  )}
                </h2>
                {done && output && (
                  <button className="btn btn-ghost" onClick={handleDownload}>
                    ↓ Preuzmi MD
                  </button>
                )}
              </div>
              <OutputViewer content={output} streaming={running} />
            </>
          ) : (
            <div className="output-empty">
              <div className="output-empty-icon">⚡</div>
              <p>Odaberi agenta i popuni formu, pa klikni <strong>Pokreni</strong>.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

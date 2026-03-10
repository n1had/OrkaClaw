import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
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

/** Find the next agent in the same stream that accepts `forma3` as input. */
function findNextAgent(registry, stream, faza) {
  if (!registry || !stream || !faza) return null
  const streamAgents = registry[stream]
  if (!streamAgents) return null
  const fazaKeys = Object.keys(streamAgents)
  const currentIdx = fazaKeys.indexOf(faza)
  if (currentIdx === -1) return null
  for (let i = currentIdx + 1; i < fazaKeys.length; i++) {
    const nextFaza = fazaKeys[i]
    const nextConfig = streamAgents[nextFaza]
    if (nextConfig.inputs?.some((f) => f.name === 'forma3')) {
      return { stream, faza: nextFaza, config: nextConfig }
    }
  }
  return null
}

export default function RunAgent({ user }) {
  const navigate = useNavigate()
  const location = useLocation()

  // Registry
  const [registry, setRegistry] = useState(null)

  // Selection
  const [selectedStream, setSelectedStream] = useState('')
  const [selectedFaza, setSelectedFaza] = useState('')
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL)

  // Inputs
  const [inputs, setInputs] = useState({})

  // Company name autocomplete
  const [companySuggestions, setCompanySuggestions] = useState([])

  // Output
  const [output, setOutput] = useState('')
  const [running, setRunning] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  // Pause / multi-turn state
  const [paused, setPaused] = useState(false)
  const [pauseInput, setPauseInput] = useState('')
  const [convMessages, setConvMessages] = useState([])
  const [convId, setConvId] = useState('')

  // Track text accumulated in the current streaming turn (for conversation history)
  const currentTurnTextRef = useRef('')
  const readerRef = useRef(null)

  // Used to pass inputs through the stream/faza-change effect without wiping them
  const prefillInputsRef = useRef(null)

  // Fetch registry on mount
  useEffect(() => {
    fetch('/registry', { credentials: 'include' })
      .then((r) => r.json())
      .then(setRegistry)
      .catch(() => setError('Nije moguće učitati registar agenata.'))
  }, [])

  // Fetch company suggestions once on mount
  useEffect(() => {
    fetch('/history/companies', { credentials: 'include' })
      .then((r) => r.ok ? r.json() : [])
      .then(setCompanySuggestions)
      .catch(() => {})
  }, [])

  // Pre-fill form from navigation state (rerun / chain from dashboard)
  useEffect(() => {
    if (!registry || !location.state?.prefill) return
    const { stream, faza, inputs: prefillInputs, model } = location.state.prefill
    prefillInputsRef.current = prefillInputs || {}
    if (model) setSelectedModel(model)
    setSelectedStream(stream)
    setSelectedFaza(faza)
    // Clear navigation state so back-navigation doesn't re-trigger
    navigate('/run', { replace: true, state: {} })
  }, [registry]) // eslint-disable-line react-hooks/exhaustive-deps

  // Reset inputs and model when agent changes
  useEffect(() => {
    if (prefillInputsRef.current) {
      setInputs(prefillInputsRef.current)
      prefillInputsRef.current = null
    } else {
      setInputs({})
    }
    setSelectedModel(registry?.[selectedStream]?.[selectedFaza]?.model ?? DEFAULT_MODEL)
  }, [selectedStream, selectedFaza]) // eslint-disable-line react-hooks/exhaustive-deps

  const agentConfig =
    registry && selectedStream && selectedFaza
      ? registry[selectedStream]?.[selectedFaza]
      : null

  // Build per-field suggestions map (only for text fields that appear in suggestions)
  const fieldSuggestions = {}
  if (agentConfig && companySuggestions.length) {
    for (const f of agentConfig.inputs) {
      if (f.type === 'text' && f.name === 'company_name') {
        fieldSuggestions[f.name] = companySuggestions
      }
    }
  }

  // Validate required inputs
  function missingRequired() {
    if (!agentConfig) return true
    return agentConfig.inputs.some(
      (f) => f.required && !inputs[f.name]?.trim()
    )
  }

  // ── Shared SSE stream reader ───────────────────────────────────────────────

  async function _streamFromBody(body) {
    const response = await fetch(`/run/${selectedStream}/${selectedFaza}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      if (response.status === 401) {
        window.location.href = '/auth/login'
        return
      }
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

      const lines = buffer.split('\n')
      buffer = lines.pop()

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
            currentTurnTextRef.current += chunk
          } else if (chunk?.type === 'init') {
            setConvMessages([{ role: 'user', content: chunk.user_message }])
            setConvId(chunk.conversation_id)
          } else if (chunk?.pause) {
            setConvMessages((prev) => [
              ...prev,
              { role: 'assistant', content: currentTurnTextRef.current },
            ])
            currentTurnTextRef.current = ''
            setPaused(true)
          } else if (chunk?.error) {
            setError(chunk.error)
          }
        } catch {
          // ignore malformed chunks
        }
      }
    }
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  async function handleRun() {
    if (missingRequired()) return
    setOutput('')
    setDone(false)
    setError('')
    setPaused(false)
    setPauseInput('')
    setConvMessages([])
    setConvId('')
    currentTurnTextRef.current = ''
    setRunning(true)

    try {
      await _streamFromBody({ ...inputs, model: selectedModel })
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  async function handleContinue() {
    if (!pauseInput.trim()) return

    const updatedMessages = [
      ...convMessages,
      { role: 'user', content: pauseInput },
    ]

    setPaused(false)
    setPauseInput('')
    currentTurnTextRef.current = ''
    setRunning(true)
    setError('')

    try {
      await _streamFromBody({
        model: selectedModel,
        conversation_id: convId,
        messages: updatedMessages,
      })
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
    setPaused(false)
  }

  function handleChainToNext() {
    const next = findNextAgent(registry, selectedStream, selectedFaza)
    if (!next) return
    navigate('/run', {
      state: {
        prefill: {
          stream: next.stream,
          faza: next.faza,
          inputs: { forma3: output },
        },
      },
    })
  }

  const canRun = agentConfig && !running && !missingRequired()
  const nextAgent = done && output ? findNextAgent(registry, selectedStream, selectedFaza) : null

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
                  suggestions={fieldSuggestions}
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
          {output || running || paused ? (
            <>
              <div className="output-toolbar">
                <h2>
                  {running ? (
                    <>
                      <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2, display: 'inline-block', verticalAlign: 'middle', marginRight: 6 }} />
                      Agent radi…
                    </>
                  ) : paused ? (
                    <>
                      <span style={{ marginRight: 6 }}>⏸</span>
                      Čeka na odgovor
                    </>
                  ) : (
                    'Output'
                  )}
                </h2>
                <div style={{ display: 'flex', gap: 8 }}>
                  {done && output && (
                    <button className="btn btn-ghost" onClick={handleDownload}>
                      ↓ Preuzmi MD
                    </button>
                  )}
                  {nextAgent && (
                    <button className="btn btn-primary" onClick={handleChainToNext}>
                      Pokreni {nextAgent.config.name} →
                    </button>
                  )}
                </div>
              </div>

              <OutputViewer content={output} streaming={running} />

              {/* PAUSE reply area */}
              {paused && (
                <div className="pause-input-area">
                  <div className="pause-label">Agent čeka vaš odgovor</div>
                  <textarea
                    className="pause-textarea"
                    value={pauseInput}
                    onChange={(e) => setPauseInput(e.target.value)}
                    placeholder="Unesite odgovor i pritisnite Nastavi (ili Ctrl+Enter)…"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                        e.preventDefault()
                        handleContinue()
                      }
                    }}
                    autoFocus
                    rows={4}
                  />
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                    <button
                      className="btn btn-ghost"
                      onClick={handleStop}
                    >
                      Odustani
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={handleContinue}
                      disabled={!pauseInput.trim()}
                    >
                      Nastavi →
                    </button>
                  </div>
                </div>
              )}
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

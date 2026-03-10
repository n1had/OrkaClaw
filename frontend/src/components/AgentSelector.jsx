export default function AgentSelector({
  registry,
  selectedStream,
  selectedFaza,
  onStreamChange,
  onFazaChange,
}) {
  if (!registry) {
    return <div style={{ color: 'var(--muted)', fontSize: 13 }}>Učitavanje…</div>
  }

  const streams = Object.keys(registry)
  const fazas = selectedStream ? Object.entries(registry[selectedStream]) : []

  return (
    <div className="agent-selector">
      <div className="field">
        <label>Stream</label>
        <select
          value={selectedStream}
          onChange={(e) => onStreamChange(e.target.value)}
        >
          <option value="">— Odaberi stream —</option>
          {streams.map((s) => (
            <option key={s} value={s}>
              {s.toUpperCase()}
            </option>
          ))}
        </select>
      </div>

      {selectedStream && (
        <div className="field">
          <label>Faza</label>
          <select
            value={selectedFaza}
            onChange={(e) => onFazaChange(e.target.value)}
          >
            <option value="">— Odaberi fazu —</option>
            {fazas.map(([key, agent]) => (
              <option key={key} value={key}>
                {agent.name}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}

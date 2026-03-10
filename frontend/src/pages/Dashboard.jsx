import { useNavigate } from 'react-router-dom'

export default function Dashboard({ user }) {
  const navigate = useNavigate()

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
          <div className="empty-state">
            Historija pokreta dolazi u sljedećem koraku.
          </div>
        </div>
      </div>
    </div>
  )
}

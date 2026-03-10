export default function Login() {
  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">Orka</div>
        <p className="login-subtitle">AI Agent Interface</p>

        <a href="/auth/login" className="btn-ms">
          <div className="ms-icon">
            <span /><span /><span /><span />
          </div>
          Prijavi se s Microsoft 365
        </a>
      </div>
    </div>
  )
}

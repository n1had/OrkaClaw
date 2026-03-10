import { useSearchParams } from 'react-router-dom'

const ERROR_MESSAGES = {
  unauthorized_domain: 'Pristup je dozvoljen samo za @orka-global.com naloge.',
}

export default function Login() {
  const [searchParams] = useSearchParams()
  const errorKey = searchParams.get('error')
  const errorMessage = errorKey ? (ERROR_MESSAGES[errorKey] ?? 'Greška pri prijavi. Pokušaj ponovo.') : null

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">Orka</div>
        <p className="login-subtitle">AI Agent Interface</p>

        {errorMessage && (
          <div className="error-box" style={{ marginBottom: 20, textAlign: 'left' }}>
            {errorMessage}
          </div>
        )}

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

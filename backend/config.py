from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_env_path = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_env_path), env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    hubspot_private_app_token: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = ""
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    secret_key: str = "changeme"
    database_url: str = "sqlite:///./orka.db"

    # Auth redirect — must match the registered redirect URI in Azure AD app registration
    redirect_uri: str = "http://localhost:8000/auth/callback"

    # Where the frontend is served from — used for post-auth redirects
    # In production: same as backend URL (e.g. https://orka.azurecontainerapps.io)
    # In development: Vite dev server (http://localhost:5173)
    frontend_url: str = "http://localhost:5173"

    # Comma-separated list of allowed CORS origins
    # In production on Azure (FastAPI serves the frontend): can be same as backend URL
    cors_origins: str = "http://localhost:5173"


settings = Settings()

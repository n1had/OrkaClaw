from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    hubspot_private_app_token: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = ""
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    secret_key: str = "changeme"
    database_url: str = "sqlite:///./orka.db"


settings = Settings()

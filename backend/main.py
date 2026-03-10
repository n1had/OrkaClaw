from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import router as auth_router
from config import settings

app = FastAPI(title="OrkaAgentInterface", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/config-check")
def config_check():
    """Verify which env vars are set (values hidden)."""
    return {
        "anthropic_api_key": bool(settings.anthropic_api_key),
        "hubspot_private_app_token": bool(settings.hubspot_private_app_token),
        "microsoft_client_id": bool(settings.microsoft_client_id),
        "microsoft_tenant_id": bool(settings.microsoft_tenant_id),
        "slack_bot_token": bool(settings.slack_bot_token),
        "database_url": settings.database_url,
    }

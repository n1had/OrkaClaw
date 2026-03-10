import json

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agents import get_agent_config, load_registry, stream_agent
from auth import get_current_user, router as auth_router
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


@app.get("/registry")
def get_registry():
    """Return the agent registry so the frontend can build dynamic forms."""
    return load_registry()


@app.post("/run/{stream}/{faza}")
async def run_agent(
    stream: str,
    faza: str,
    inputs: dict = Body(default={}),
    current_user: dict = Depends(get_current_user),
):
    """Stream agent output as Server-Sent Events (text/event-stream)."""
    try:
        get_agent_config(stream, faza)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    async def event_stream():
        try:
            async for chunk in stream_agent(stream, faza, inputs):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

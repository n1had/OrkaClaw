import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agents import get_agent_config, load_registry, stream_agent
from auth import get_current_user, router as auth_router
from config import settings
from database import SessionLocal, init_db
from models import Run
from slack_bot import handler as slack_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OrkaAgentInterface", version="0.1.0", lifespan=lifespan)

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.post("/slack/events")
async def slack_events(req: Request):
    if slack_handler is None:
        raise HTTPException(status_code=503, detail="Slack bot not configured")
    return await slack_handler.handle(req)


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
    body: dict = Body(default={}),
    current_user: dict = Depends(get_current_user),
):
    """Stream agent output as Server-Sent Events. Saves completed run to DB."""
    try:
        config = get_agent_config(stream, faza)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Extract optional model override; the rest of the body is form inputs
    model: str | None = body.get("model") or None
    inputs = {k: v for k, v in body.items() if k != "model"}

    microsoft_token = current_user.get("ms_access_token", "")

    async def event_stream():
        chunks: list[str] = []
        error_occurred = False

        try:
            async for chunk in stream_agent(stream, faza, inputs, microsoft_token, model):
                chunks.append(chunk)
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            error_occurred = True
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

        # Persist to DB only on successful, non-empty runs.
        # Executes when the consumer reads past the final [DONE] event.
        if chunks and not error_occurred:
            db = SessionLocal()
            try:
                db.add(Run(
                    user_email=current_user["email"],
                    user_name=current_user["name"],
                    stream=stream,
                    faza=faza,
                    agent_name=config.get("name", f"{stream}/{faza}"),
                    inputs_json=json.dumps(inputs),
                    output_markdown="".join(chunks),
                ))
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── History endpoints ────────────────────────────────────────────────────────

@app.get("/history")
def get_history(current_user: dict = Depends(get_current_user)):
    """Return the current user's 50 most recent runs (no output text)."""
    db = SessionLocal()
    try:
        runs = (
            db.query(Run)
            .filter(Run.user_email == current_user["email"])
            .order_by(Run.created_at.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": r.id,
                "stream": r.stream,
                "faza": r.faza,
                "agent_name": r.agent_name,
                "inputs": json.loads(r.inputs_json),
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ]
    finally:
        db.close()


@app.get("/history/{run_id}")
def get_run(run_id: int, current_user: dict = Depends(get_current_user)):
    """Return a single run's full output. Only the run's owner can access it."""
    db = SessionLocal()
    try:
        run = (
            db.query(Run)
            .filter(Run.id == run_id, Run.user_email == current_user["email"])
            .first()
        )
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return {
            "id": run.id,
            "stream": run.stream,
            "faza": run.faza,
            "agent_name": run.agent_name,
            "inputs": json.loads(run.inputs_json),
            "output_markdown": run.output_markdown,
            "created_at": run.created_at.isoformat(),
        }
    finally:
        db.close()


# ── Production: serve the built React SPA ────────────────────────────────────
# When `backend/static/` exists (Dockerfile copies `frontend/dist` there),
# FastAPI serves the frontend from the same origin — no separate web server needed.

_STATIC_DIR = Path(__file__).parent / "static"

if _STATIC_DIR.is_dir():
    _assets_dir = _STATIC_DIR / "assets"
    if _assets_dir.is_dir():
        # Serve hashed JS/CSS bundles
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="static-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Catch-all: serve index.html for any path not matched by the API above."""
        # Serve exact static files (favicon.ico, etc.) when they exist
        target = (_STATIC_DIR / full_path).resolve()
        static_root = _STATIC_DIR.resolve()
        if target.is_relative_to(static_root) and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_STATIC_DIR / "index.html"))

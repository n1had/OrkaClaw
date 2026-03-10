import json
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agents import get_agent_config, load_registry, stream_agent
from auth import get_current_user, router as auth_router
from config import settings
from database import SessionLocal, init_db
from models import Run


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OrkaAgentInterface", version="0.1.0", lifespan=lifespan)

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
    """Stream agent output as Server-Sent Events. Saves completed run to DB."""
    try:
        config = get_agent_config(stream, faza)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    microsoft_token = current_user.get("ms_access_token", "")

    async def event_stream():
        chunks: list[str] = []
        error_occurred = False

        try:
            async for chunk in stream_agent(stream, faza, inputs, microsoft_token):
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

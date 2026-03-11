import json
import uuid as _uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agents import (
    filter_registry_for_user,
    get_agent_config,
    load_registry,
    prepare_initial_messages,
    stream_agent,
    user_can_access_agent,
)
from auth import (
    get_current_user,
    is_ms_token_expired,
    reissue_session_cookie,
    try_refresh_ms_token,
    router as auth_router,
)
from config import settings
from database import SessionLocal, init_db
from models import AVAILABLE_MODELS, Run
from slack_bot import handler as slack_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OrkaClaw", version="0.1.0", lifespan=lifespan)

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
def get_registry(current_user: dict = Depends(get_current_user)):
    """Return the agent registry filtered to agents the current user can access."""
    return filter_registry_for_user(load_registry(), current_user["email"])


@app.get("/models")
def get_models():
    return {"models": AVAILABLE_MODELS}


# ── PAUSE detection helpers ───────────────────────────────────────────────────

_PAUSE_MARKER = "[PAUSE]"
_PAUSE_LEN = len(_PAUSE_MARKER)

# In-memory store for multi-turn PAUSE runs.
# conv_id → {stream, faza, user_email, user_name, agent_name, inputs_json, output_so_far}
# TODO: add TTL-based cleanup to prevent unbounded memory growth.
_pending_runs: dict[str, dict] = {}


def _split_on_pause(buffer: str) -> tuple[str, bool, str]:
    """Scan buffer for the [PAUSE] control marker.

    Returns (safe_text, pause_found, new_buffer):
      - safe_text   : text that is safe to emit right now
      - pause_found : True when [PAUSE] was detected inside safe_text's tail
      - new_buffer  : remaining text to prepend to the next incoming chunk
    """
    idx = buffer.find(_PAUSE_MARKER)
    if idx != -1:
        # Emit everything before the marker; discard the marker itself.
        # Text after the marker is dropped (agent shouldn't generate past PAUSE).
        return buffer[:idx], True, ""

    # No complete marker found yet.  Hold back up to PAUSE_LEN-1 trailing
    # characters in case the marker is split across chunk boundaries.
    hold = 0
    for i in range(_PAUSE_LEN - 1, 0, -1):
        if buffer.endswith(_PAUSE_MARKER[:i]):
            hold = i
            break
    return buffer[: len(buffer) - hold], False, buffer[len(buffer) - hold :]


# ── Run endpoint ──────────────────────────────────────────────────────────────

@app.post("/run/{stream}/{faza}")
async def run_agent(
    stream: str,
    faza: str,
    body: dict = Body(default={}),
    current_user: dict = Depends(get_current_user),
):
    """Stream agent output as Server-Sent Events.

    Supports multi-turn PAUSE/continue conversations:
      - Initial run:      body contains form inputs (+ optional model override)
      - Continuation run: body contains {model, conversation_id, messages: [...]}
    """
    # ── Extract special fields ────────────────────────────────────────────────
    model: str | None = body.get("model") or None
    conv_id_from_client: str | None = body.get("conversation_id")
    messages_from_client: list[dict] | None = body.get("messages")
    # Remaining keys are the agent's form inputs (empty for continuation runs)
    inputs = {
        k: v
        for k, v in body.items()
        if k not in ("model", "conversation_id", "messages")
    }

    # ── Validate ──────────────────────────────────────────────────────────────
    if not messages_from_client:
        # Initial run — verify the agent exists and user has access
        try:
            agent_cfg = get_agent_config(stream, faza)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        if not user_can_access_agent(agent_cfg, current_user["email"]):
            raise HTTPException(status_code=403, detail="Nemate pristup ovom agentu.")
    else:
        # Continuation — conversation_id must reference a live pending run
        if not conv_id_from_client or conv_id_from_client not in _pending_runs:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired conversation_id. Start a new run.",
            )

    # ── MS token refresh ──────────────────────────────────────────────────────
    microsoft_token = current_user.get("ms_access_token", "")
    refreshed_tokens: dict | None = None

    if microsoft_token and is_ms_token_expired(current_user):
        refreshed_tokens = try_refresh_ms_token(current_user.get("home_account_id", ""))
        if refreshed_tokens:
            microsoft_token = refreshed_tokens["access_token"]
        else:
            raise HTTPException(status_code=401, detail="ms_token_expired")

    # ── SSE generator ─────────────────────────────────────────────────────────

    async def event_stream():
        turn_chunks: list[str] = []
        error_occurred = False
        active_conv_id = conv_id_from_client  # may be reassigned for new runs

        try:
            # ── Build or receive conversation messages ────────────────────────
            if not messages_from_client:
                # Initial run: fetch CRM context, build first user message
                agent_config, messages = await prepare_initial_messages(
                    stream, faza, inputs, microsoft_token
                )
                active_conv_id = str(_uuid.uuid4())
                _pending_runs[active_conv_id] = {
                    "stream": stream,
                    "faza": faza,
                    "user_email": current_user["email"],
                    "user_name": current_user["name"],
                    "agent_name": agent_config.get("name", f"{stream}/{faza}"),
                    "inputs_json": json.dumps(inputs),
                    "output_so_far": "",
                }
                # Emit init event so the frontend can track the conversation
                yield (
                    f"data: {json.dumps({'type': 'init', 'conversation_id': active_conv_id, 'user_message': messages[0]['content']})}\n\n"
                )
            else:
                # Continuation run: use messages provided by the frontend
                messages = messages_from_client

            # ── Stream with PAUSE detection ───────────────────────────────────
            buffer = ""
            paused = False

            async for chunk in stream_agent(stream, faza, messages, model):
                buffer += chunk
                safe_text, pause_found, buffer = _split_on_pause(buffer)

                if safe_text:
                    turn_chunks.append(safe_text)
                    yield f"data: {json.dumps(safe_text)}\n\n"

                if pause_found:
                    paused = True
                    break  # Stop consuming; discard any text generated past [PAUSE]

            # Flush held-back buffer tail (only when not paused)
            if buffer and not paused:
                turn_chunks.append(buffer)
                yield f"data: {json.dumps(buffer)}\n\n"

            if paused:
                # Accumulate this turn's output for eventual DB save
                if active_conv_id and active_conv_id in _pending_runs:
                    _pending_runs[active_conv_id]["output_so_far"] += "".join(turn_chunks)
                yield 'data: {"pause": true}\n\n'
                return  # Do NOT emit [DONE]; the run continues after user replies

        except Exception as e:
            error_occurred = True
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            if active_conv_id and active_conv_id in _pending_runs:
                del _pending_runs[active_conv_id]

        yield "data: [DONE]\n\n"

        # ── Persist to DB on successful completion ────────────────────────────
        if not error_occurred:
            prior_output = ""
            if active_conv_id and active_conv_id in _pending_runs:
                meta = _pending_runs.pop(active_conv_id)
                prior_output = meta.get("output_so_far", "")
            else:
                # Fallback (should not normally be reached)
                meta = {
                    "stream": stream,
                    "faza": faza,
                    "user_email": current_user["email"],
                    "user_name": current_user["name"],
                    "agent_name": f"{stream}/{faza}",
                    "inputs_json": json.dumps(inputs),
                }

            full_output = prior_output + "".join(turn_chunks)
            if full_output:
                db = SessionLocal()
                try:
                    db.add(Run(
                        user_email=meta["user_email"],
                        user_name=meta["user_name"],
                        stream=meta["stream"],
                        faza=meta["faza"],
                        agent_name=meta["agent_name"],
                        inputs_json=meta["inputs_json"],
                        output_markdown=full_output,
                    ))
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()

    response = StreamingResponse(event_stream(), media_type="text/event-stream")
    # If the MS token was silently refreshed, bake the new token into the
    # session cookie so subsequent requests don't re-trigger the refresh.
    if refreshed_tokens:
        reissue_session_cookie(
            response,
            current_user,
            refreshed_tokens["access_token"],
            refreshed_tokens["ms_token_exp"],
        )
    return response


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


@app.get("/history/companies")
def get_companies(current_user: dict = Depends(get_current_user)):
    """Return unique company names from the user's runs for autocomplete."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Run.inputs_json)
            .filter(Run.user_email == current_user["email"])
            .all()
        )
        companies: set[str] = set()
        for (inputs_json,) in rows:
            try:
                inp = json.loads(inputs_json)
                name = inp.get("company_name", "")
                if name:
                    companies.add(name)
            except Exception:
                pass
        return sorted(companies)
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

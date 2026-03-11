# OrkaAgentInterface — Agent Handoff Summary

## 1. Project Purpose

OrkaAgentInterface is an internal web platform and Slack bot for the Orka team to run AI agents through a unified UI. Users authenticate via Microsoft 365 (orka-global.com only), fill out structured forms, and receive streamed Markdown output from AI agents backed by Anthropic, OpenAI, or Google Gemini. Each run is saved to a database and downloadable.

## 2. Architecture Overview

```
Browser (React/Vite) ──SSE──► FastAPI backend ──► AI APIs (Anthropic / OpenAI / Gemini)
                                    │
                          ┌─────────┴─────────┐
                        SQLite            orka_agents/
                        (runs DB)         (git submodule — agent MD specs)
```

- **Frontend**: React SPA (`frontend/src/`), Vite dev server on port 5173, proxies `/api` to port 8000.
- **Backend**: FastAPI (`backend/main.py`), served on port 8000. In production, serves the compiled SPA from `backend/static/`.
- **Agent specs**: Live in `backend/orka_agents/agents/` (git submodule, OrkaAgents repo). Read-only here — edit upstream.

## 3. Key Modules and Responsibilities

| File | Responsibility |
|------|---------------|
| `backend/main.py` | FastAPI app, all HTTP endpoints, SSE streaming with PAUSE detection, DB persistence |
| `backend/agents.py` | Agent registry loading (auto-discovery + JSON overrides), system prompt builder, multi-provider streaming (`_stream_anthropic`, `_stream_openai`, `_stream_gemini`) |
| `backend/auth.py` | Microsoft Azure AD OAuth flow, session cookie, token refresh |
| `backend/hubspot.py` | HubSpot CRM context fetch for agent user messages |
| `backend/outlook.py` | Microsoft Graph API — Outlook email context |
| `backend/slack_bot.py` | Slack Bolt `/run` and `/orka` commands (optional — app starts without Slack tokens) |
| `backend/models.py` | SQLAlchemy `Run` model |
| `backend/database.py` | DB engine + session factory (SQLite locally) |
| `backend/config.py` | `Settings` dataclass, all env vars via `.env` |
| `backend/agent_registry.json` | Optional overrides on top of auto-discovered agents |

### Frontend pages
- `Login.jsx` — Microsoft OAuth redirect
- `Dashboard.jsx` — Agent selector + run history
- `RunAgent.jsx` — Form + SSE stream viewer with PAUSE/continue support

## 4. Important Conventions and Constraints

- **Agent naming**: Agent MD files must match `{stream}_{faza}_*.md` (e.g. `m1_f1_agent.md`). Stream and faza are extracted from the filename.
- **YAML frontmatter**: Agent MD files may have optional YAML frontmatter (`---` block) defining `name`, `model`, `inputs`, `references`, `allowed_users`, `hubspot_company_field`. If absent, sensible defaults apply.
- **Registry merge order**: `agent_registry.json` overrides auto-discovered agents at the stream/faza level.
- **Access control**: `allowed_users` list in agent config (case-insensitive email match). Empty = all authenticated users.
- **Model routing** (in `agents.py:_detect_provider`):
  - `claude-*` → Anthropic
  - `gemini-*` → Google Gemini
  - anything else → OpenAI
- **Default model**: `claude-sonnet-4-6` (set in `agents.py:DEFAULT_MODEL`).
- **PAUSE protocol**: Agent outputs `[PAUSE]` marker mid-stream. Backend detects it, emits `{"pause": true}` SSE event, and holds state in `_pending_runs` dict (in-memory, no TTL yet). Frontend resumes by POSTing `{conversation_id, messages: [...]}` to the same endpoint.
- **Never commit**: `.env`, `backend/orka.db`.
- **Agent specs are read-only** in this repo — all edits go to the OrkaAgents upstream repo.
- **Auth**: All `/run`, `/registry`, `/history` endpoints require a valid Azure AD session cookie.

## 5. Build / Run / Test Commands

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload          # dev server on :8000

# Frontend
cd frontend
npm install
npm run dev                        # dev server on :5173 (proxies to :8000)
npm run build                      # outputs to frontend/dist/

# Update agent submodule
git submodule update --remote

# Health check
curl http://localhost:8000/health
curl http://localhost:8000/config-check   # shows which env vars are set
```

There are no automated tests currently.

## 6. Current Development Focus

**Priority 3 — Run history improvements** (in progress, commit `4fe15bd`):

- Company name autocomplete (`/history/companies` endpoint exists)
- Load a previous run's output from history (`/history/{run_id}` exists)
- Rerun same agent with same inputs
- Chain F1 output into F2 (`forma3` auto-populated from most recent F1 run for the same company)

**Already complete:**
- P1: PAUSE points with multi-turn conversation (backend + frontend)
- P2: Auto-discovery of agents from `orka_agents/agents/`
- P4: Role-based access per agent (`allowed_users` in registry)

## 7. Run Lifecycle

1. User signs in with Microsoft 365 using an orka-global.com account.
2. User opens the web app or Slack bot and selects an available agent.
3. The system loads the agent definition from backend/orka_agents/agents/.
4. User provides required inputs and selects the model/provider configuration.
5. A run is created and persisted in SQLite.
6. The backend executes the agent run and streams progress/results to the UI via Server-Sent Events.
7. The user can review the live output, then view the completed run later from run history.
8. Completed runs can be reopened, downloaded, or rerun with the same inputs.
9. Where supported, outputs from one phase (for example F1) can be reused as inputs for the next phase (for example F2).
10. A run ends when execution completes, fails, or is stopped, and its final state is stored for later access.

## 8. Known Technical Debt and Risks

| Issue | Location | Risk |
|-------|----------|------|
| `_pending_runs` has no TTL/cleanup | `main.py:91` | Unbounded memory growth if runs are abandoned mid-PAUSE |
| Extended thinking disabled for Anthropic | `agents.py:_stream_anthropic` | Multi-turn thinking blocks not captured; re-enable once thinking-block handling is added |
| SQLite in production | `backend/orka.db` | Not suitable for concurrent writes or Azure deployment; migrate to Azure SQL |
| No automated tests | — | Refactors are unvalidated |
| Slack uses shared service account for Outlook | `slack_bot.py` | Emails fetched for all users come from one account, not the individual user |
| No TTL on in-memory conversation store | `main.py:_pending_runs` | Server restart loses all paused conversations |

## Current Risks
- No automated tests
- Paused conversations are stored only in memory

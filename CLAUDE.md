# OrkaAgentInterface

## What this is
A web platform and Slack bot that allows Orka team members to run AI agents through a unified interface. Users authenticate with Microsoft 365 (orka-global.com accounts only). Each agent run takes structured input, calls an AI API, and returns output in the browser and as a downloadable MD file.

## Project structure
```
OrkaAgentInterface/
├── backend/
│   ├── main.py              # FastAPI app, all endpoints
│   ├── auth.py              # Microsoft Azure AD OAuth flow
│   ├── agents.py            # Agent runner — Anthropic, OpenAI, Gemini
│   ├── hubspot.py           # HubSpot API integration
│   ├── outlook.py           # Microsoft Graph API (Outlook)
│   ├── slack_bot.py         # Slack Bolt — /run and /orka commands
│   ├── models.py            # SQLAlchemy Run model
│   ├── database.py          # DB engine and session
│   ├── config.py            # Settings from .env
│   ├── agent_registry.json  # Agent definitions
│   └── orka_agents/         # Git submodule — OrkaAgents repo
│       ├── agents/          # Agent MD specs
│       └── reference/       # Workflow, mapa, playbook files
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── pages/
│       │   ├── Login.jsx
│       │   ├── Dashboard.jsx
│       │   └── RunAgent.jsx
│       └── components/
│           ├── AgentSelector.jsx
│           ├── InputForm.jsx
│           └── OutputViewer.jsx
├── BACKLOG.md               # Prioritized feature backlog
├── SPEC.md                  # Original build specification
└── .env                     # Never commit — see .env.example
```

## How to run locally

**Backend:**
```bash
cd backend
uvicorn main:app --reload
```

**Frontend:**
```bash
cd frontend
npm run dev
```

Frontend runs on `http://localhost:5173`, proxies API calls to `http://localhost:8000`.

## Environment variables
See `.env.example` for all required variables. Key ones:
- `ANTHROPIC_API_KEY` — Anthropic API
- `HUBSPOT_PRIVATE_APP_TOKEN` — HubSpot private app token
- `MICROSOFT_CLIENT_ID/SECRET/TENANT_ID` — Azure AD app registration
- `OPENAI_API_KEY` — OpenAI API (optional)
- `GOOGLE_API_KEY` — Google Gemini API (optional)
- `SLACK_BOT_TOKEN/SIGNING_SECRET` — Slack bot (optional)

## Agent system
Agents are defined in `backend/agent_registry.json`. Each agent has:
- `spec` — path to agent MD file in `orka_agents/agents/`
- `references` — list of reference MD files injected into prompt
- `inputs` — field definitions for the dynamic web form
- `model` — default AI model (can be overridden in UI)

Agent specs live in the `orka_agents/` git submodule (OrkaAgents repo). To update agents:
```bash
git submodule update --remote
```

## Auth
- Microsoft Azure AD OAuth only
- Restricted to `@orka-global.com` accounts
- User's Microsoft token is stored in session and used for Outlook calls

## Multi-provider AI
`agents.py` detects provider from model name prefix:
- `claude-` → Anthropic
- `gpt-` or `o` → OpenAI
- `gemini-` → Google Gemini

## Database
SQLite locally (`backend/orka.db`). Tables created automatically on startup. Each run saved with user email, agent info, inputs, and full markdown output.

## Key rules
- Never commit `.env` or `backend/orka.db`
- Agent specs are read-only in this repo — edit them in OrkaAgents repo
- All `/run` endpoints require valid Azure AD session
- Slack bot is optional — app starts normally without Slack tokens
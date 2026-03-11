# Orka Claw — Build Spec v1.0

## Overview
A web platform and Slack bot that allows Orka team members to run AI agents (m1 f1, m1 f2, and future agents) through a unified interface. Users authenticate with Microsoft 365. Each agent run takes structured input, calls Claude API with the appropriate agent spec, and returns output in the browser and as a downloadable MD file.

---

## Tech Stack
- **Backend:** Python, FastAPI
- **Frontend:** React (single page)
- **Auth:** Microsoft OAuth 2.0 (Azure AD) — Microsoft 365 accounts
- **Database:** SQLite locally, Azure SQL on deploy (stores sessions, run history)
- **Claude:** Anthropic API (`claude-sonnet-4-20250514`)
- **HubSpot:** HubSpot API (private app token from environment variable)
- **Outlook:** Microsoft Graph API (per-user OAuth token)
- **Slack:** Slack Bolt for Python
- **Deploy target:** Azure (later — build locally first)

---

## Project Structure

```
OrkaAgentInterface/
├── backend/
│   ├── main.py               # FastAPI app entry point
│   ├── auth.py               # Microsoft OAuth flow
│   ├── agents.py             # Agent runner logic
│   ├── hubspot.py            # HubSpot API calls
│   ├── outlook.py            # Microsoft Graph / Outlook calls
│   ├── slack_bot.py          # Slack Bolt app
│   ├── models.py             # DB models
│   ├── config.py             # Environment config
│   └── agent_specs/          # Copy of agent MD files
│       ├── m1_f1_agent.md
│       ├── m1_f2_agent.md
│       └── ...
├── frontend/
│   ├── index.html
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── Login.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   └── RunAgent.jsx
│   │   └── components/
│   │       ├── AgentSelector.jsx
│   │       ├── InputForm.jsx
│   │       └── OutputViewer.jsx
├── .env
└── README.md
```

---

## Authentication

- Login with Microsoft 365 (Azure AD OAuth 2.0)
- After login, store user session + Microsoft access token (for Outlook calls)
- Session persists across browser refreshes (JWT or server session)
- No separate username/password — Microsoft account is the only login method

---

## Agent Registry

Define all available agents in a registry (JSON or Python dict). This is what drives the UI dropdowns and Slack command parsing.

```json
{
  "m1": {
    "f1": {
      "name": "M1 Faza 1 — Istraživanje i klasifikacija",
      "spec": "agent_specs/m1_f1_agent.md",
      "inputs": ["company_name", "website", "channel", "notes"],
      "output_file": "m1_f1_forma3.md"
    },
    "f2": {
      "name": "M1 Faza 2 — Inicijalni kontakt",
      "spec": "agent_specs/m1_f2_agent.md",
      "inputs": ["forma3"],
      "output_file": "m1_f2_log.md"
    }
  }
}
```

New agents are added by dropping a new spec file and adding a registry entry — no code changes needed.

---

## Web Interface

### Login page
- "Prijavi se s Microsoft 365" button
- Microsoft OAuth redirect flow

### Dashboard
- List of recent agent runs (user's own runs)
- "Pokreni agenta" button

### Run Agent page

**Step 1 — Select agent**
Dropdown: Stream (M1, D2, ...) → Faza (F1, F2, ...)

**Step 2 — Input form**
Dynamic form based on agent registry inputs. For m1 f1:
- Company name (required)
- Website (optional)
- Channel (dropdown: Lista kompanija / Direktni ulaz / CRM / Konferencija)
- Notes (free text, optional)

**Step 3 — Run**
"Pokreni" button → shows live streaming output from Claude as it runs

**Step 4 — Output**
- Forma 3 rendered in browser (Markdown → HTML)
- "Preuzmi MD" download button
- "Spremi u historiju" (auto-saved)

---

## Backend — Agent Runner

When an agent run is triggered:

1. Load agent spec from `agent_specs/[agent].md`
2. Build system prompt from spec
3. Build user message from input fields
4. Inject HubSpot context — search HubSpot for company, attach results to prompt
5. Inject Outlook context — search user's Outlook for company name, attach email summary to prompt
6. Call Claude API (streaming)
7. Stream response back to frontend
8. Save completed output to DB (run history)

### Claude API call structure
```python
messages = [
    {
        "role": "user",
        "content": f"""
Company: {company_name}
Website: {website}
Channel: {channel}
Notes: {notes}

--- HubSpot data ---
{hubspot_context}

--- Outlook data ---
{outlook_context}

Run the agent according to your instructions.
        """
    }
]
```

---

## HubSpot Integration

- Use HubSpot private app token (stored in `.env`)
- On each agent run, search for company by name
- Extract: company record, contacts, deal stage, activity log, notes
- Return as structured text injected into Claude prompt
- Shared token — same for all users

---

## Outlook Integration

- Use Microsoft Graph API with per-user OAuth token (from login)
- On each agent run, search user's Outlook for company name + any contact names found in HubSpot
- Extract: email threads, dates, key content
- Return as structured summary injected into Claude prompt
- Each user sees only their own emails

---

## Slack Bot

Command format: `/run m1 f1 [company name]`

Example: `/run m1 f1 hifa oil`

### Flow
1. Slack sends POST to `/slack/events`
2. Parse stream, faza, company name from command
3. Look up agent in registry
4. Run agent (same runner as web — shared function)
5. Post output to Slack channel as formatted message + MD file attachment

### Additional commands
- `/run m1 f2` — triggers f2 agent (requires f1 output already exists for that company)
- `/orka status` — shows recent runs

### Auth note
Slack bot uses a shared HubSpot token. For Outlook, Slack runs use a designated service account (no per-user Outlook in Slack — this is a known limitation).

---

## Environment Variables (.env)

```
ANTHROPIC_API_KEY=
HUBSPOT_PRIVATE_APP_TOKEN=
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=
SLACK_BOT_TOKEN=
SLACK_SIGNING_SECRET=
SECRET_KEY=  # for session/JWT signing
DATABASE_URL=sqlite:///./orka.db
```

---

## Build Order

Build in this exact order — each step is testable before moving to the next:

1. **FastAPI skeleton** — health check endpoint, config loading
2. **Microsoft OAuth** — login flow, session storage
3. **Agent runner** — Claude API call with hardcoded m1 f1, no MCP yet
4. **Web UI** — input form, output viewer, download button
5. **HubSpot integration** — search and inject into prompt
6. **Outlook integration** — Graph API search and inject
7. **Run history** — save and display past runs
8. **Slack bot** — `/run` command, shared runner
9. **Polish + Azure deploy prep**

---

## Out of Scope (v1)
- Per-user HubSpot accounts
- Slack per-user Outlook (uses service account)
- Role-based access control
- Agent output editing in browser
- Automated follow-up scheduling

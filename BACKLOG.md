# OrkaAgentInterface — Backlog

## Priority 1 — PAUSE points in F2 agent
**Problem:** F2 agent has defined PAUSE points where it waits for human input before continuing (after Step 3, Step 7, Step 8). The current UI streams output but has no way to receive mid-run input — the agent can't pause and wait.

**Solution:** Add a conversational interface to the Run page. When the agent outputs a PAUSE signal, the stream pauses and a text input appears for the user to respond. The response is sent back to the agent which continues from that point.

**Requirements:**
- Detect PAUSE signal in streamed output (agent outputs a specific marker e.g. `[PAUSE]`)
- Stop streaming, show input field
- Send user reply back to backend
- Backend continues the conversation with full history
- Stream resumes until next PAUSE or completion
- Works for any agent that uses PAUSE points, not just F2

---

## Priority 2 — Auto-discovery of agents
**Problem:** Adding a new agent requires manually editing `agent_registry.json`. This is error-prone and requires developer access.

**Solution:** Backend scans the `orka_agents/agents/` folder on startup and auto-registers any `.md` file it finds. Registry metadata (inputs, references, model) is either inferred from the filename or defined in a frontmatter block at the top of the agent MD file.

**Requirements:**
- On startup, scan `orka_agents/agents/` for `*.md` files
- Parse optional YAML frontmatter in agent MD files for metadata (inputs, references, model)
- If no frontmatter: use sensible defaults (company_name input, matching reference files by naming convention)
- `agent_registry.json` becomes optional/override only
- New agent appears in UI dropdown automatically after backend restart

---

## Priority 3 — Run history improvements
**Problem:** Run history exists in DB but UI is basic. No way to load a previous company, rerun an agent, or chain F1 output into F2.

**Solution:**
- Company name autocomplete — as user types, suggest companies from previous runs
- Load previous run — click a history entry to load its output in the viewer
- Rerun — button to rerun the same agent with same inputs
- Chain to next phase — after F1 completes, show "Pokreni F2" button that pre-fills F2 with F1 output

**Requirements:**
- `/history` endpoint returns unique company names for autocomplete
- Run viewer shows full output with download option (already exists, improve UI)
- Rerun sends same inputs to `/run/{stream}/{faza}`
- F2 input (`forma3`) auto-populated from most recent F1 run for same company

---

## Priority 4 — Role-based access per agent
**Problem:** All logged-in users can run all agents. Some agents should be restricted to certain team members.

**Solution:** Define allowed users or roles per agent in the registry. On login, user's email determines which agents they can see and run.

**Requirements:**
- Add `allowed_users` or `allowed_roles` field to agent registry (empty = all users)
- `/registry` endpoint filters agents based on logged-in user's email
- UI only shows agents the user has access to
- Backend validates access on every `/run` call
- Admin can manage access — initially via registry file, later via UI

---

## Backlog — Future
- Web UI for managing agent specs (create, edit, upload MD files)
- Slack per-user Outlook (currently uses shared service account)
- Azure deploy — Container Apps, Azure SQL, CI/CD pipeline
- Python orchestrator for multi-agent workflows
- D2 stream agents
- M1 Faza 3 agent (EC Vodič)
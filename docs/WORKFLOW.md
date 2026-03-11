# Development Workflow

## Branching

Work directly on `master` for small changes. For larger features, branch from `master` and open a PR.

## Making changes

1. Read the relevant files before editing — don't guess at structure.
2. Check `BACKLOG.md` for priority ordering before starting new work.
3. Keep frontend and backend changes in the same commit when they're coupled.
4. If you add a new backend endpoint called from the frontend, verify it's covered by the Vite proxy in `frontend/vite.config.js`.

## Harnesses

- `AGENTS.md` is the shared repository handoff for coding agents.
- `CLAUDE.md` is the Claude-facing quick reference for the same repo.
- Harness switching does not change the development rules: both Claude Code and Codex should follow this workflow and use `docs/DECISIONS.md` for ADRs.

## Agent specs

Agent MD files live in `backend/orka_agents/` (git submodule). **Do not edit them here.** Push changes to the OrkaAgents repo, then pull the submodule:

```bash
git submodule update --remote
```

## Secrets and data

- Never commit `.env` or `backend/orka.db`.
- Never hardcode API keys, tokens, or credentials.

## Architecture Decision Records (ADRs)

Write an ADR in `docs/DECISIONS.md` whenever a decision meets **any** of these criteria:

- It changes how providers, models, or the agent registry work.
- It introduces or removes a cross-cutting pattern (auth, streaming, PAUSE protocol, DB schema).
- It changes how the frontend and backend communicate (new SSE event types, new API contracts).
- It affects how agent specs are discovered, merged, or overridden.
- A reasonable developer would ask "why did we do it this way?" when reading the code.

Use the template at the top of `docs/DECISIONS.md`. One ADR per decision; keep them short.

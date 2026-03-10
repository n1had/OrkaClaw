"""Outlook / Microsoft Graph integration — per-user OAuth token."""

import logging
import httpx

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TIMEOUT = 10.0      # seconds per request
_MAX_EMAILS = 8      # emails to include in context
_PREVIEW_LEN = 300   # characters of body preview per email


# ── Auth header ──────────────────────────────────────────────────────────────

def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Low-level fetcher ────────────────────────────────────────────────────────

async def _search_emails(
    client: httpx.AsyncClient,
    token: str,
    query: str,
) -> list[dict]:
    """Return up to _MAX_EMAILS messages whose subject/body/sender mention `query`."""
    resp = await client.get(
        f"{_GRAPH_BASE}/me/messages",
        headers=_h(token),
        params={
            "$search": f'"{query}"',
            "$top": _MAX_EMAILS,
            "$select": "subject,from,toRecipients,receivedDateTime,bodyPreview",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


# ── Formatter ────────────────────────────────────────────────────────────────

def _fmt_emails(emails: list[dict], company_name: str) -> str:
    if not emails:
        return f'### Outlook emails\nNone found mentioning "{company_name}".'
    lines = [f"### Outlook emails ({len(emails)} most recent)"]
    for msg in emails:
        subject  = msg.get("subject") or "(no subject)"
        date     = (msg.get("receivedDateTime") or "")[:10]
        from_obj = (msg.get("from") or {}).get("emailAddress", {})
        sender   = from_obj.get("name") or from_obj.get("address", "Unknown")
        preview  = (msg.get("bodyPreview") or "").strip()
        if len(preview) > _PREVIEW_LEN:
            preview = preview[:_PREVIEW_LEN] + "…"
        lines.append(f"- [{date}] **{subject}** — From: {sender}")
        if preview:
            lines.append(f"  > {preview}")
    return "\n".join(lines)


# ── Public entry point ───────────────────────────────────────────────────────

async def get_outlook_context(company_name: str, microsoft_token: str) -> str:
    """
    Search the current user's Outlook for emails mentioning `company_name`.
    Returns a formatted Markdown block ready to inject into the Claude prompt.

    Never raises — all errors are returned as a human-readable string
    so an Outlook failure never breaks the agent run.
    """
    if not microsoft_token:
        return "_(Outlook token not available — user must re-authenticate)_"

    if not company_name or not company_name.strip():
        return "_(No company name provided — Outlook lookup skipped)_"

    try:
        async with httpx.AsyncClient() as client:
            emails = await _search_emails(client, microsoft_token, company_name.strip())

        return "\n\n".join([
            f"## Outlook — {company_name}",
            _fmt_emails(emails, company_name),
        ])

    except httpx.TimeoutException:
        logger.warning("Outlook request timed out for query %r", company_name)
        return "_(Outlook request timed out)_"
    except httpx.HTTPStatusError as e:
        logger.error(
            "Outlook API HTTP %s for query %r — response: %s",
            e.response.status_code,
            company_name,
            e.response.text[:500],
            exc_info=True,
        )
        return f"_(Outlook API error: HTTP {e.response.status_code})_"
    except Exception:
        logger.exception("Unexpected Outlook error for query %r", company_name)
        return "_(Outlook error — see server logs)_"

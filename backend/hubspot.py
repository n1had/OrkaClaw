"""HubSpot CRM integration — shared private-app token, all users."""

import asyncio
import httpx

from config import settings

_BASE = "https://api.hubapi.com"
_TIMEOUT = 10.0       # seconds per request
_MAX_ITEMS = 5        # contacts / deals / notes to fetch
_NOTE_PREVIEW = 500   # characters to show per note


# ── Auth header ─────────────────────────────────────────────────────────────

def _h() -> dict:
    return {
        "Authorization": f"Bearer {settings.hubspot_private_app_token}",
        "Content-Type": "application/json",
    }


# ── Low-level fetchers ───────────────────────────────────────────────────────

async def _search_company(client: httpx.AsyncClient, name: str) -> dict | None:
    """Return first HubSpot company whose name contains `name`, or None."""
    resp = await client.post(
        f"{_BASE}/crm/v3/objects/companies/search",
        headers=_h(),
        json={
            "filterGroups": [{"filters": [{
                "propertyName": "name",
                "operator": "CONTAINS_TOKEN",
                "value": name,
            }]}],
            "properties": [
                "name", "domain", "industry",
                "city", "country", "numberofemployees",
                "lifecyclestage", "hs_lead_status", "description",
            ],
            "limit": 1,
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


async def _assoc_ids(client: httpx.AsyncClient, company_id: str, to: str) -> list[str]:
    """Return up to _MAX_ITEMS IDs of `to`-type objects associated with the company."""
    resp = await client.get(
        f"{_BASE}/crm/v3/objects/companies/{company_id}/associations/{to}",
        headers=_h(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return [r["id"] for r in resp.json().get("results", [])][:_MAX_ITEMS]


async def _batch_read(
    client: httpx.AsyncClient,
    object_type: str,
    ids: list[str],
    properties: list[str],
) -> list[dict]:
    """Batch-read HubSpot objects by IDs."""
    if not ids:
        return []
    resp = await client.post(
        f"{_BASE}/crm/v3/objects/{object_type}/batch/read",
        headers=_h(),
        json={"inputs": [{"id": i} for i in ids], "properties": properties},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


async def _get_contacts(client: httpx.AsyncClient, company_id: str) -> list[dict]:
    ids = await _assoc_ids(client, company_id, "contacts")
    return await _batch_read(
        client, "contacts", ids,
        ["firstname", "lastname", "email", "phone", "jobtitle"],
    )


async def _get_deals(client: httpx.AsyncClient, company_id: str) -> list[dict]:
    ids = await _assoc_ids(client, company_id, "deals")
    return await _batch_read(
        client, "deals", ids,
        ["dealname", "dealstage", "pipeline", "amount", "closedate"],
    )


async def _get_notes(client: httpx.AsyncClient, company_id: str) -> list[dict]:
    ids = await _assoc_ids(client, company_id, "notes")
    return await _batch_read(
        client, "notes", ids,
        ["hs_note_body", "hs_timestamp"],
    )


# ── Formatters ───────────────────────────────────────────────────────────────

def _fmt_company(props: dict) -> str:
    lines = ["### Company record"]
    for label, key in [
        ("Name",            "name"),
        ("Domain",          "domain"),
        ("Industry",        "industry"),
        ("City",            "city"),
        ("Country",         "country"),
        ("Employees",       "numberofemployees"),
        ("Lifecycle stage", "lifecyclestage"),
        ("Lead status",     "hs_lead_status"),
    ]:
        val = props.get(key) or "—"
        lines.append(f"- **{label}:** {val}")
    desc = (props.get("description") or "").strip()
    if desc:
        lines.append(f"- **Description:** {desc[:300]}")
    return "\n".join(lines)


def _fmt_contacts(contacts: list[dict]) -> str:
    if not contacts:
        return "### Contacts\nNone found."
    lines = [f"### Contacts ({len(contacts)})"]
    for c in contacts:
        p = c.get("properties", {})
        name = f"{p.get('firstname', '')} {p.get('lastname', '')}".strip() or "Unknown"
        parts = [f"**{name}**"]
        if p.get("jobtitle"):  parts.append(p["jobtitle"])
        if p.get("email"):     parts.append(p["email"])
        if p.get("phone"):     parts.append(p["phone"])
        lines.append("- " + " — ".join(parts))
    return "\n".join(lines)


def _fmt_deals(deals: list[dict]) -> str:
    if not deals:
        return "### Deals\nNone found."
    lines = [f"### Deals ({len(deals)})"]
    for d in deals:
        p = d.get("properties", {})
        name = p.get("dealname") or "Unnamed deal"
        parts = [f"**{name}**"]
        if p.get("dealstage"):  parts.append(f"Stage: {p['dealstage']}")
        if p.get("pipeline"):   parts.append(f"Pipeline: {p['pipeline']}")
        if p.get("amount"):     parts.append(f"Amount: {p['amount']}")
        if p.get("closedate"):  parts.append(f"Close: {p['closedate'][:10]}")
        lines.append("- " + " — ".join(parts))
    return "\n".join(lines)


def _fmt_notes(notes: list[dict]) -> str:
    if not notes:
        return "### Notes\nNone found."
    lines = [f"### Notes ({len(notes)})"]
    for n in notes:
        p = n.get("properties", {})
        ts    = (p.get("hs_timestamp") or "")[:10]
        body  = (p.get("hs_note_body") or "").strip()
        preview = body[:_NOTE_PREVIEW] + ("…" if len(body) > _NOTE_PREVIEW else "")
        lines.append(f"- [{ts}] {preview}")
    return "\n".join(lines)


# ── Public entry point ───────────────────────────────────────────────────────

async def get_hubspot_context(company_name: str) -> str:
    """
    Fetch CRM data for `company_name` and return a formatted Markdown block
    ready to be injected into the Claude prompt.

    Never raises — all errors are returned as a human-readable string
    so a HubSpot failure never breaks the agent run.
    """
    if not settings.hubspot_private_app_token:
        return "_(HubSpot token not configured)_"

    if not company_name or not company_name.strip():
        return "_(No company name provided — HubSpot lookup skipped)_"

    try:
        async with httpx.AsyncClient() as client:
            company = await _search_company(client, company_name.strip())

            if not company:
                return f'_(Company "{company_name}" not found in HubSpot)_'

            company_id  = company["id"]
            props       = company.get("properties", {})
            found_name  = props.get("name", company_name)

            # Fetch contacts / deals / notes concurrently; don't fail if one errors
            contacts, deals, notes = await asyncio.gather(
                _get_contacts(client, company_id),
                _get_deals(client, company_id),
                _get_notes(client, company_id),
                return_exceptions=True,
            )
            contacts = contacts if not isinstance(contacts, Exception) else []
            deals    = deals    if not isinstance(deals,    Exception) else []
            notes    = notes    if not isinstance(notes,    Exception) else []

        return "\n\n".join([
            f"## HubSpot — {found_name} (ID: {company_id})",
            _fmt_company(props),
            _fmt_contacts(contacts),
            _fmt_deals(deals),
            _fmt_notes(notes),
        ])

    except httpx.TimeoutException:
        return "_(HubSpot request timed out)_"
    except httpx.HTTPStatusError as e:
        return f"_(HubSpot API error: HTTP {e.response.status_code})_"
    except Exception as e:
        return f"_(HubSpot error: {e})_"

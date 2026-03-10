import json
from pathlib import Path
from typing import AsyncIterator

import anthropic
from google import genai as google_genai
from google.genai import types as genai_types
import openai as openai_sdk

from config import settings
from hubspot import get_hubspot_context
from outlook import get_outlook_context

BACKEND_DIR = Path(__file__).parent
REGISTRY_PATH = BACKEND_DIR / "agent_registry.json"

DEFAULT_MODEL = "claude-sonnet-4-6"

# OpenAI reasoning models use max_completion_tokens instead of max_tokens
_OPENAI_REASONING_MODELS = {"o1", "o1-mini", "o3", "o3-mini", "o4-mini"}


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def get_agent_config(stream: str, faza: str) -> dict:
    registry = load_registry()
    try:
        return registry[stream][faza]
    except KeyError:
        raise ValueError(f"Agent '{stream}/{faza}' nije pronađen u registru")


def _detect_provider(model: str) -> str:
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "gemini"
    return "openai"  # gpt-*, o3, o4-mini, etc.


def _read(relative_path: str) -> str:
    return (BACKEND_DIR / relative_path).read_text(encoding="utf-8")


def _build_system_prompt(config: dict) -> str:
    """Concatenate agent spec + all reference files into one system prompt."""
    parts = [_read(config["spec"])]
    for ref_path in config.get("references", []):
        filename = Path(ref_path).name
        parts.append(f"\n\n---\n\n# Reference: {filename}\n\n{_read(ref_path)}")
    parts.append(
        "\n\n---\n\n"
        "# Web app context\n\n"
        "You are running inside the Orka web application. "
        "Inputs are provided directly in the user message — there are no local files to read. "
        "Do not attempt to read inputs/ or outputs/ paths. "
        "Write your full output as Markdown in this conversation."
    )
    return "".join(parts)


def _build_user_message(
    inputs: dict,
    fields: list,
    hubspot_context: str = "",
    outlook_context: str = "",
) -> str:
    """Format web form inputs + CRM/email context into a structured message."""
    lines = []
    for field in fields:
        name  = field["name"]
        label = field.get("label", name)
        value = inputs.get(name) or "N/A"
        lines.append(f"**{label}:** {value}")

    lines += [
        "",
        "--- HubSpot data ---",
        hubspot_context or "_(not yet integrated)_",
        "",
        "--- Outlook data ---",
        outlook_context or "_(not yet integrated)_",
        "",
        "Run the agent according to your instructions.",
    ]
    return "\n".join(lines)


# ── Per-provider streaming helpers ────────────────────────────────────────────

async def _stream_anthropic(
    model: str, system_prompt: str, user_message: str
) -> AsyncIterator[str]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    async with client.messages.stream(
        model=model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as s:
        async for text in s.text_stream:
            yield text


async def _stream_openai(
    model: str, system_prompt: str, user_message: str
) -> AsyncIterator[str]:
    client = openai_sdk.AsyncOpenAI(api_key=settings.openai_api_key)
    token_kwarg = (
        {"max_completion_tokens": 8000}
        if model in _OPENAI_REASONING_MODELS
        else {"max_tokens": 8000}
    )
    stream = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        stream=True,
        **token_kwarg,
    )
    async for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            yield content


async def _stream_gemini(
    model: str, system_prompt: str, user_message: str
) -> AsyncIterator[str]:
    client = google_genai.Client(api_key=settings.google_api_key)
    async for chunk in client.aio.models.generate_content_stream(
        model=model,
        contents=user_message,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=8000,
        ),
    ):
        if chunk.text:
            yield chunk.text


# ── Public interface ──────────────────────────────────────────────────────────

async def stream_agent(
    stream: str,
    faza: str,
    inputs: dict,
    microsoft_token: str = "",
    model: str | None = None,   # overrides registry default
) -> AsyncIterator[str]:
    """Async generator yielding text chunks from whichever provider is selected."""
    config = get_agent_config(stream, faza)

    # Resolution order: explicit override → registry default → global default
    resolved_model = model or config.get("model") or DEFAULT_MODEL

    system_prompt = _build_system_prompt(config)

    hs_field = config.get("hubspot_company_field", "")
    company_name = inputs.get(hs_field, "") if hs_field else ""
    hubspot_context = await get_hubspot_context(company_name)
    outlook_context = await get_outlook_context(company_name, microsoft_token)

    user_message = _build_user_message(
        inputs,
        config["inputs"],
        hubspot_context=hubspot_context,
        outlook_context=outlook_context,
    )

    provider = _detect_provider(resolved_model)

    if provider == "anthropic":
        async for chunk in _stream_anthropic(resolved_model, system_prompt, user_message):
            yield chunk
    elif provider == "openai":
        async for chunk in _stream_openai(resolved_model, system_prompt, user_message):
            yield chunk
    elif provider == "gemini":
        async for chunk in _stream_gemini(resolved_model, system_prompt, user_message):
            yield chunk

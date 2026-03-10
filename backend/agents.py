import json
import anthropic
from pathlib import Path

from config import settings

BACKEND_DIR = Path(__file__).parent
REGISTRY_PATH = BACKEND_DIR / "agent_registry.json"


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def get_agent_config(stream: str, faza: str) -> dict:
    registry = load_registry()
    try:
        return registry[stream][faza]
    except KeyError:
        raise ValueError(f"Agent '{stream}/{faza}' nije pronađen u registru")


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


def _build_user_message(inputs: dict, fields: list) -> str:
    """Format web form inputs into a structured message."""
    lines = []
    for field in fields:
        name = field["name"]
        label = field.get("label", name)
        value = inputs.get(name) or "N/A"
        lines.append(f"**{label}:** {value}")

    lines += [
        "",
        "--- HubSpot data ---",
        "(not yet integrated)",
        "",
        "--- Outlook data ---",
        "(not yet integrated)",
        "",
        "Run the agent according to your instructions.",
    ]
    return "\n".join(lines)


async def stream_agent(stream: str, faza: str, inputs: dict):
    """Async generator yielding text chunks from Claude for any registered agent."""
    config = get_agent_config(stream, faza)
    system_prompt = _build_system_prompt(config)
    user_message = _build_user_message(inputs, config["inputs"])

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as s:
        async for text in s.text_stream:
            yield text

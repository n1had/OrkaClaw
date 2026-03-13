"""WorkflowAgents compiler — runs prompts via Claude Agent SDK."""

from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, StreamEvent, TextBlock

from config import settings

_PROJECT_ROOT = Path(__file__).parent.parent

DEFAULT_COMPILER_MODEL = "claude-sonnet-4-6"


def _resolve_cwd() -> Path:
    """Return absolute path to the WorkflowAgents submodule."""
    path = _PROJECT_ROOT / settings.workflow_agent_repo_path
    return path.resolve()


async def stream_compiler(
    prompt: str, model: str | None = None
) -> AsyncIterator[str]:
    """Run a prompt inside the WorkflowAgents repo via Claude Agent SDK.

    Streams text chunks back to the caller.  Only Read and Write tools
    are allowed — no Bash or other tools.
    """
    cwd = _resolve_cwd()
    options = ClaudeAgentOptions(
        cwd=cwd,
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"],
        model=model or DEFAULT_COMPILER_MODEL,
        permission_mode="bypassPermissions",
    )

    last_text_len = 0

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            # Extract text from content blocks, yielding only new text
            for block in message.content:
                if isinstance(block, TextBlock):
                    new_text = block.text[last_text_len:]
                    if new_text:
                        last_text_len = len(block.text)
                        yield new_text

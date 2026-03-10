"""Slack Bolt app — /run and /orka commands."""

import asyncio
import json
import logging

from agents import load_registry, stream_agent
from config import settings
from database import SessionLocal
from models import Run

logger = logging.getLogger(__name__)

# Only initialise the Slack app when credentials are present.
# Without them the server still starts normally; /slack/events returns 503.
if settings.slack_bot_token and settings.slack_signing_secret:
    from slack_bolt.async_app import AsyncApp
    from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

    app = AsyncApp(
        token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
    )
    handler = AsyncSlackRequestHandler(app)
else:
    logger.warning(
        "SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET not set — Slack bot disabled."
    )
    app = None
    handler = None


# ── Background task ───────────────────────────────────────────────────────────

async def _run_and_post(
    client,
    channel: str,
    slack_user_id: str,
    stream: str,
    faza: str,
    inputs: dict,
    agent_name: str,
) -> None:
    """Collect agent output, persist to DB, then post result to Slack."""
    try:
        chunks: list[str] = []
        async for chunk in stream_agent(stream, faza, inputs, microsoft_token=""):
            chunks.append(chunk)
        output = "".join(chunks)

        # Persist to DB
        db = SessionLocal()
        try:
            db.add(Run(
                user_email=f"slack:{slack_user_id}",
                user_name=f"Slack user {slack_user_id}",
                stream=stream,
                faza=faza,
                agent_name=agent_name,
                inputs_json=json.dumps(inputs),
                output_markdown=output,
            ))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

        # Post preview (Slack text field limit ~4000 chars)
        label = inputs.get("company_name") or faza
        if len(output) > 2800:
            preview = output[:2800] + "\n\n_(truncated — full output attached as file)_"
        else:
            preview = output

        await client.chat_postMessage(
            channel=channel,
            text=f"*{agent_name} — {label}*\n\n{preview}",
            mrkdwn=True,
        )

        # Upload full MD file
        filename = f"{stream}_{faza}_{label.replace(' ', '_')}.md"
        await client.files_upload_v2(
            channel=channel,
            content=output,
            filename=filename,
            title=f"{stream.upper()} {faza.upper()} — {label}",
        )

    except Exception as exc:
        await client.chat_postMessage(
            channel=channel,
            text=f":x: Agent run failed: `{exc}`",
        )


# ── Slash command handlers (only registered when Slack is configured) ─────────

if app is not None:

    @app.command("/run")
    async def handle_run(ack, command, client) -> None:
        """
        /run <stream> <faza> [company name]

        Examples:
          /run m1 f1 hifa oil
          /run m1 f2              (uses most recent f1 output)
          /run m1 f2 hifa oil     (uses most recent f1 output for that company)
        """
        await ack()

        text = (command.get("text") or "").strip()
        parts = text.split()
        channel = command["channel_id"]
        slack_user = command["user_id"]

        if len(parts) < 2:
            await client.chat_postMessage(
                channel=channel,
                text=(
                    ":warning: Usage: `/run <stream> <faza> [company name]`\n"
                    "Example: `/run m1 f1 hifa oil`"
                ),
            )
            return

        stream = parts[0].lower()
        faza = parts[1].lower()
        extra = " ".join(parts[2:])  # company name or other trailing text

        # Validate agent exists
        try:
            registry = load_registry()
            agent_cfg = registry[stream][faza]
            agent_name = agent_cfg.get("name", f"{stream}/{faza}")
        except KeyError:
            available = ", ".join(
                f"`/run {s} {f}`"
                for s, fazas in load_registry().items()
                for f in fazas
            )
            await client.chat_postMessage(
                channel=channel,
                text=f":warning: Unknown agent `{stream}/{faza}`. Available: {available}",
            )
            return

        # Build inputs
        if faza == "f2":
            # f2 needs forma3 from a previous f1 run
            db = SessionLocal()
            try:
                q = db.query(Run).filter(Run.stream == stream, Run.faza == "f1")
                if extra:
                    # filter by company name if provided
                    q = q.filter(Run.inputs_json.contains(extra))
                last_f1 = q.order_by(Run.created_at.desc()).first()
            finally:
                db.close()

            if not last_f1:
                msg = (
                    f":warning: No previous `{stream}/f1` run found"
                    + (f" for *{extra}*" if extra else "")
                    + f". Run `/run {stream} f1 <company>` first."
                )
                await client.chat_postMessage(channel=channel, text=msg, mrkdwn=True)
                return

            inputs = {"forma3": last_f1.output_markdown}
            company_name = json.loads(last_f1.inputs_json).get("company_name", extra or "unknown")
        else:
            if not extra:
                await client.chat_postMessage(
                    channel=channel,
                    text=f":warning: Please provide a company name: `/run {stream} {faza} <company name>`",
                )
                return
            inputs = {"company_name": extra}
            company_name = extra

        await client.chat_postMessage(
            channel=channel,
            text=(
                f":hourglass_flowing_sand: Running *{agent_name}* for *{company_name}*...\n"
                f"I'll post the result here when done."
            ),
            mrkdwn=True,
        )

        asyncio.create_task(
            _run_and_post(client, channel, slack_user, stream, faza, inputs, agent_name)
        )

    @app.command("/orka")
    async def handle_orka(ack, command, client) -> None:
        """/orka status — show 10 most recent runs across all users."""
        await ack()

        text = (command.get("text") or "").strip().lower()
        channel = command["channel_id"]

        if text != "status":
            await client.chat_postMessage(
                channel=channel,
                text=(
                    ":information_source: *Orka commands:*\n"
                    "• `/orka status` — show recent agent runs\n"
                    "• `/run <stream> <faza> [company]` — run an agent\n\n"
                    "*Examples:*\n"
                    "• `/run m1 f1 hifa oil`\n"
                    "• `/run m1 f2 hifa oil`"
                ),
                mrkdwn=True,
            )
            return

        db = SessionLocal()
        try:
            runs = db.query(Run).order_by(Run.created_at.desc()).limit(10).all()
        finally:
            db.close()

        if not runs:
            await client.chat_postMessage(channel=channel, text="No runs yet.")
            return

        lines = ["*Recent agent runs (last 10):*"]
        for r in runs:
            inp = json.loads(r.inputs_json)
            company = inp.get("company_name", "—")
            ts = r.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"• `{r.stream.upper()} {r.faza.upper()}` — {company} — {ts} — {r.user_name}"
            )

        await client.chat_postMessage(channel=channel, text="\n".join(lines), mrkdwn=True)

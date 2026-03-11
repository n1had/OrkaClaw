"""SQLAlchemy ORM models."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


AVAILABLE_MODELS = [
    {"id": "claude-sonnet-4-6", "provider": "anthropic"},
    {"id": "claude-opus-4-6", "provider": "anthropic"},
    {"id": "claude-haiku-4-5-20251001", "provider": "anthropic"},
    {"id": "gpt-5", "provider": "openai"},
    {"id": "gpt-5-mini", "provider": "openai"},
    {"id": "gpt-5-nano", "provider": "openai"},
    {"id": "gpt-4.1", "provider": "openai"},
    {"id": "gpt-4.1-mini", "provider": "openai"},
    {"id": "gpt-4.1-nano", "provider": "openai"},
    {"id": "gpt-4o", "provider": "openai"},
    {"id": "gpt-4o-mini", "provider": "openai"},
    {"id": "o1", "provider": "openai"},
    {"id": "o1-mini", "provider": "openai"},
    {"id": "o3", "provider": "openai"},
    {"id": "o3-mini", "provider": "openai"},
    {"id": "o4-mini", "provider": "openai"},
    {"id": "gemini-2.0-flash", "provider": "gemini"},
    {"id": "gemini-2.5-pro", "provider": "gemini"},
]


def get_provider_for_model(model_id: str) -> str:
    for model in AVAILABLE_MODELS:
        if model["id"] == model_id:
            return model["provider"]
    raise ValueError(f"Unknown model '{model_id}'. Add it to backend/models.py.")


class Base(DeclarativeBase):
    pass


class Run(Base):
    """A single completed agent run, owned by one user."""

    __tablename__ = "runs"

    id              = Column(Integer, primary_key=True, index=True)
    user_email      = Column(String, index=True, nullable=False)
    user_name       = Column(String, nullable=False)
    stream          = Column(String(10), nullable=False)
    faza            = Column(String(10), nullable=False)
    agent_name      = Column(String(200), nullable=False)
    inputs_json     = Column(Text, nullable=False)   # JSON-encoded form inputs
    output_markdown = Column(Text, nullable=False)
    created_at      = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

"""SQLAlchemy ORM models."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


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

"""SQLAlchemy engine, session factory, and DB initialisation."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models import Base

# SQLite requires check_same_thread=False in async/threaded contexts.
# Other drivers (Azure SQL, Postgres) don't need it.
_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(settings.database_url, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables that don't yet exist. Safe to call on every startup."""
    Base.metadata.create_all(bind=engine)

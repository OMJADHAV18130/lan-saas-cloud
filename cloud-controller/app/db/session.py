"""Database engine / session management.

SQLite stores METADATA ONLY (users, file records, audit events).
File contents always live in HDFS.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    # check_same_thread is required for SQLite + FastAPI's threadpool executors.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
    future=True,
)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):  # noqa: ANN001
    """Enable foreign keys + WAL on SQLite for better consistency behaviour."""
    if not _is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                            expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

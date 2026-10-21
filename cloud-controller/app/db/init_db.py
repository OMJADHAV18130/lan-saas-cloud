"""Database initialisation helper (used at startup and by tests)."""
from __future__ import annotations

import logging

from app.db.base import Base
from app.db.session import engine

# Importing the models registers them on Base.metadata.
from app.models import audit, file, user  # noqa: F401

logger = logging.getLogger("cloud_controller.db")


def create_all() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema is ready.")

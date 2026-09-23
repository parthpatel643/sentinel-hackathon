"""Database layer: async SQLAlchemy engine/session, ORM models."""

from core_api.db.base import Base, get_engine, get_session, get_sessionmaker
from core_api.db.models import (
    Alert,
    AuditLogEntry,
    Camera,
    Department,
    Detection,
    EvidenceClip,
    FieldSightingReport,
    Site,
    StreamProfile,
    User,
    WatchlistEntry,
)

__all__ = [
    "Alert",
    "AuditLogEntry",
    "Base",
    "Camera",
    "Department",
    "Detection",
    "EvidenceClip",
    "FieldSightingReport",
    "Site",
    "StreamProfile",
    "User",
    "WatchlistEntry",
    "get_engine",
    "get_session",
    "get_sessionmaker",
]

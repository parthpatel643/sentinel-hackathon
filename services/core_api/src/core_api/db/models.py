"""Registry ORM models — the persisted system of record for Model 1.

Deliberately narrower than `sentinel_core.schemas.CameraDescriptor`, which is
the wire/catalogue-facing shape: this is the storage shape. A mapping
function (`camera_from_descriptor` in core_api/registry/service.py) converts
one into the other, so a catalogue quirk never leaks into the schema.

Camera health here is "latest known state" only (status, last_seen_at) — a
full time-series history (TimescaleDB hypertable, per docs/01-ARCHITECTURE.md
section 7) is an M4 concern, deliberately out of scope for the registry.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import JSON, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core_api.db.base import Base

__all__ = ["Camera", "Department", "Site", "StreamProfile"]


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(unique=True)
    code: Mapped[str | None] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    sites: Mapped[list[Site]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )
    cameras: Mapped[list[Camera]] = relationship(back_populates="department")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE")
    )
    name: Mapped[str]
    location: Mapped[str | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    department: Mapped[Department] = relationship(back_populates="sites")
    cameras: Mapped[list[Camera]] = relationship(back_populates="site")


class Camera(Base):
    """Primary key is the catalogue's own string camera_id (e.g. `cam01`,
    `dev-cam-01`), not a surrogate — this makes catalogue-driven upsert a
    plain `ON CONFLICT (camera_id) DO UPDATE`, with no id-lookup layer."""

    __tablename__ = "cameras"

    camera_id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    driver_id: Mapped[str]
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))

    location: Mapped[str | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326))
    fov: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326),
        comment="Field-of-view coverage polygon — makes gap analysis a real "
        "coverage-shape query, not dots on a map.",
    )

    tier: Mapped[str] = mapped_column(default="b_sampled")
    status: Mapped[str] = mapped_column(default="unknown")
    last_seen_at: Mapped[datetime | None]

    source: Mapped[str] = mapped_column(
        default="manual", comment="gov_catalogue | manual | bulk_csv | api"
    )
    attributes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    department: Mapped[Department | None] = relationship(back_populates="cameras")
    site: Mapped[Site | None] = relationship(back_populates="cameras")
    profiles: Mapped[list[StreamProfile]] = relationship(
        back_populates="camera", cascade="all, delete-orphan"
    )


class StreamProfile(Base):
    """One way of consuming a camera (RTSP/HLS/WHEP/ONVIF) — a camera
    usually has several. Mirrors sentinel_core.schemas.StreamProfile."""

    __tablename__ = "stream_profiles"
    __table_args__ = (UniqueConstraint("camera_id", "protocol", name="uq_camera_protocol"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id", ondelete="CASCADE"))
    protocol: Mapped[str]
    url: Mapped[str]
    codec: Mapped[str | None]
    width: Mapped[int | None]
    height: Mapped[int | None]
    declared_fps: Mapped[float | None]

    camera: Mapped[Camera] = relationship(back_populates="profiles")

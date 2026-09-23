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

__all__ = [
    "Alert",
    "Camera",
    "Department",
    "Detection",
    "EvidenceClip",
    "FieldSightingReport",
    "Site",
    "StreamProfile",
    "User",
    "WatchlistEntry",
]


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

    # "Latest known state" health only — a full time-series history is
    # deliberately out of scope for the registry table itself (M3 decision);
    # M4 adds these columns because the edge worker needs somewhere to
    # report live status, but does not add a hypertable for it yet.
    measured_fps: Mapped[float | None] = mapped_column(
        comment="Derived from PTS by the edge worker — never the declared rate"
    )
    declared_fps: Mapped[float | None]
    reconnects: Mapped[int] = mapped_column(default=0)
    discontinuities: Mapped[int] = mapped_column(default=0)

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


class Detection(Base):
    """One ANPR read — the persisted twin of `sentinel_core.schemas.Event`
    (type=anpr.plate_read). `observed_at` (derived from stream_epoch + PTS,
    never arrival time — ADR-005) is the hypertable partitioning column; see
    the migration for the `create_hypertable()` call, which SQLAlchemy has no
    native construct for.

    `event_id` is the ULID from the originating Event, kept as the natural
    key so a detection is traceable back to the exact pipeline run that
    produced it — required for evidentiary provenance, not just convenience.
    """

    __tablename__ = "detections"
    __table_args__ = (UniqueConstraint("event_id", "observed_at", name="uq_detection_event"),)

    # TimescaleDB requires the partitioning column (observed_at) to be part
    # of every unique/primary-key constraint on a hypertable — a composite
    # primary key, not a single surrogate id, or create_hypertable() refuses
    # with "cannot create a unique index without the partitioning column".
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    observed_at: Mapped[datetime] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[str]
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id", ondelete="CASCADE"))

    plate_text: Mapped[str]
    plate_normalised: Mapped[str] = mapped_column(index=True)
    plate_ambiguity_key: Mapped[str] = mapped_column(index=True)
    plate_confidence: Mapped[float]
    format_valid: Mapped[bool] = mapped_column(default=False)
    frames_voted: Mapped[int] = mapped_column(default=1)

    vehicle_class: Mapped[str | None]
    vehicle_track_id: Mapped[str | None]

    bbox_x: Mapped[int | None]
    bbox_y: Mapped[int | None]
    bbox_width: Mapped[int | None]
    bbox_height: Mapped[int | None]

    pts_ms: Mapped[float]

    snapshot_uri: Mapped[str | None]
    node_id: Mapped[str]
    model_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WatchlistEntry(Base):
    """A plate the correlation engine is actively watching for. Matched
    against every incoming Detection by `correlator.py`'s matching ladder —
    rungs 1-2 (exact, OCR-ambiguity-class) for this milestone; edit-distance
    and partial/wildcard matching (rungs 3-4 in docs/01-ARCHITECTURE.md
    section 6.1) are a documented next step, not silently dropped."""

    __tablename__ = "watchlist_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plate_normalised: Mapped[str] = mapped_column(index=True)
    plate_ambiguity_key: Mapped[str] = mapped_column(index=True)
    entry_type: Mapped[str] = mapped_column(comment="stolen | wanted | missing | suspect | bolo")
    priority: Mapped[str] = mapped_column(
        default="medium", comment="low | medium | high | critical"
    )
    case_reference: Mapped[str | None]
    requested_by: Mapped[str | None]
    notes: Mapped[str | None]
    active: Mapped[bool] = mapped_column(default=True)
    valid_from: Mapped[datetime] = mapped_column(server_default=func.now())
    valid_until: Mapped[datetime | None] = mapped_column(
        comment="Expired entries stop matching automatically — purpose limitation, "
        "not just a UI filter"
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    alerts: Mapped[list[Alert]] = relationship(back_populates="watchlist_entry")


class Alert(Base):
    """A watchlist hit. Deduplicated: the same plate at the same camera
    within a sliding window collapses into one alert with a rising
    sighting_count, rather than spamming one row per frame."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    watchlist_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watchlist_entries.id", ondelete="CASCADE")
    )
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id", ondelete="CASCADE"))
    detection_event_id: Mapped[str]

    plate_text: Mapped[str]
    match_rung: Mapped[str] = mapped_column(comment="exact | ambiguity_class")
    match_confidence: Mapped[float]
    priority_score: Mapped[float]

    status: Mapped[str] = mapped_column(
        default="new",
        comment="new | acknowledged | assigned | in_progress | resolved | false_positive",
    )
    sighting_count: Mapped[int] = mapped_column(default=1)
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]

    resolved_by: Mapped[str | None]
    resolution_note: Mapped[str | None]

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    watchlist_entry: Mapped[WatchlistEntry] = relationship(back_populates="alerts")
    camera: Mapped[Camera] = relationship()


class User(Base):
    """An Operator Console account. `role` is a plain string, not an enum,
    so adding a role later is a data migration, not a schema one.

    `department_id` (M12) is the ABAC attribute the Postgres RLS policies
    on cameras/detections/alerts are keyed on — `NULL` means "not scoped to
    one department" (sees/writes everything, the natural default for an
    HQ/admin account), a set value means "restricted to that department's
    cameras, plus any camera with no department assigned yet." See
    docs/08-SECURITY-HARDENING.md."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]
    full_name: Mapped[str]
    role: Mapped[str] = mapped_column(default="operator", comment="operator | admin")
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class EvidenceClip(Base):
    """A sealed, hashed event clip for one alert — docs/01-ARCHITECTURE.md
    section 6.5's "on alert, a sealed pre/post-roll clip" (M7). Recording
    only turns on for the seal window (Model 4 is event-driven, not a
    statewide archive — see infra/compose/mediamtx.yml), so this captures
    footage from the moment sealing was requested onward, not truly before
    the alert; the alert's own detection snapshot is the closest thing to a
    "before" artefact until a rolling pre-roll buffer is a real requirement.
    `sha256`/`manifest` are only populated once `status` reaches `sealed` —
    a tamper check must hash the actual delivered bytes, not a promise."""

    __tablename__ = "evidence_clips"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), index=True
    )
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id", ondelete="CASCADE"))

    status: Mapped[str] = mapped_column(default="pending", comment="pending | sealed | failed")
    file_path: Mapped[str | None]
    sha256: Mapped[str | None]
    manifest: Mapped[dict[str, object] | None] = mapped_column(JSON)
    duration_s: Mapped[float | None]
    error: Mapped[str | None]

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sealed_at: Mapped[datetime | None]

    alert: Mapped[Alert] = relationship()
    camera: Mapped[Camera] = relationship()


class FieldSightingReport(Base):
    """A plate an officer reported by hand from the Field PWA (docs/03-UX-
    DESIGN.md §5.3) — distinct from a `Detection`, which is always a
    machine ANPR read off a fixed camera. `client_report_id` is generated
    on the device the moment the officer taps submit, before the report
    ever reaches the network: the PWA's offline outbox retries the same
    submission until it succeeds, and a flaky connection must not turn one
    tap into two reports server-side."""

    __tablename__ = "field_sighting_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_report_id: Mapped[str] = mapped_column(unique=True, index=True)
    reported_by: Mapped[str]
    plate_text: Mapped[str]
    lat: Mapped[float | None]
    lon: Mapped[float | None]
    notes: Mapped[str | None]
    photo_path: Mapped[str | None]

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

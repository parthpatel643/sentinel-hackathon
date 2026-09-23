"""add zones and zone_events tables

Revision ID: 6943898d1be1
Revises: 3a9af9c7bca1
Create Date: 2026-09-23 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6943898d1be1"
down_revision: str | Sequence[str] | None = "3a9af9c7bca1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same department-tenancy RLS pattern as migration 23c60ee4c006 — zones/
# zone_events are camera-scoped just like detections/alerts, so they get
# the same policy shape (unrestricted when unset/NULL, otherwise scoped to
# that department's own cameras plus any camera with no department yet).
_CAMERA_JOIN_TENANCY_CLAUSE = (
    "current_setting('app.current_department_id', true) IS NULL "
    "OR current_setting('app.current_department_id', true) = '' "
    "OR camera_id IN ("
    "  SELECT camera_id FROM cameras WHERE department_id IS NULL "
    "  OR department_id::text = current_setting('app.current_department_id', true)"
    ")"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "rule_type",
            sa.String(),
            nullable=False,
            comment="intrusion | loitering | wrong_way | stopped_vehicle",
        ),
        sa.Column("polygon", sa.JSON(), nullable=False),
        sa.Column("dwell_threshold_s", sa.Float(), nullable=False),
        sa.Column("expected_direction_deg", sa.Float(), nullable=False),
        sa.Column("direction_tolerance_deg", sa.Float(), nullable=False),
        sa.Column("stopped_speed_threshold", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.camera_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "zone_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("track_id", sa.String(), nullable=False),
        sa.Column("dwell_time_s", sa.Float(), nullable=True),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.camera_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_zone_events_observed_at"), "zone_events", ["observed_at"], unique=False
    )

    for table in ("zones", "zone_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY department_tenancy ON {table} "
            f"USING ({_CAMERA_JOIN_TENANCY_CLAUSE}) WITH CHECK ({_CAMERA_JOIN_TENANCY_CLAUSE})"
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("zones", "zone_events"):
        op.execute(f"DROP POLICY IF EXISTS department_tenancy ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_zone_events_observed_at"), table_name="zone_events")
    op.drop_table("zone_events")
    op.drop_table("zones")

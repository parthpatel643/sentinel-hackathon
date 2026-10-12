"""add camera_events: cameras whose view changed (moved, turned away, obstructed)

Revision ID: b7d2e4f6a8c0
Revises: a3c5e7f9b1d2
Create Date: 2026-10-12 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d2e4f6a8c0"
down_revision: str | Sequence[str] | None = "a3c5e7f9b1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Department tenancy, the same shape as zone_events (migration 6943898d1be1).
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
        "camera_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("camera_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, comment="view_shifted | view_unrecognised"),
        sa.Column(
            "shift_pct",
            sa.Float(),
            nullable=True,
            comment="Displacement of the view as a percentage of the frame width",
        ),
        sa.Column("rotation_deg", sa.Float(), nullable=True),
        sa.Column("scale", sa.Float(), nullable=True),
        sa.Column(
            "match_ratio",
            sa.Float(),
            nullable=True,
            comment="Matched fixed points as a share of those in the remembered view",
        ),
        sa.Column("has_snapshots", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Processing time. Ordering only; never display it.",
        ),
        sa.Column(
            "camera_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="The camera's burned-in clock on the frame the change was confirmed on",
        ),
        sa.Column(
            "status",
            sa.String(),
            server_default="new",
            nullable=False,
            comment="new | acknowledged | resolved | false_positive",
        ),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column(
            "restored_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the edge saw the view line up with the remembered one again",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.camera_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(op.f("ix_camera_events_observed_at"), "camera_events", ["observed_at"])
    op.create_index(op.f("ix_camera_events_status"), "camera_events", ["status"])
    op.execute("ALTER TABLE camera_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE camera_events FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY department_tenancy ON camera_events "
        f"USING ({_CAMERA_JOIN_TENANCY_CLAUSE}) WITH CHECK ({_CAMERA_JOIN_TENANCY_CLAUSE})"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS department_tenancy ON camera_events")
    op.drop_index(op.f("ix_camera_events_status"), table_name="camera_events")
    op.drop_index(op.f("ix_camera_events_observed_at"), table_name="camera_events")
    op.drop_table("camera_events")

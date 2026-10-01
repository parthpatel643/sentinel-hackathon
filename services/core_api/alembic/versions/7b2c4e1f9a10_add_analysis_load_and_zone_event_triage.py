"""add analysis load to cameras and triage state to zone events

Revision ID: 7b2c4e1f9a10
Revises: 6943898d1be1
Create Date: 2026-10-01 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b2c4e1f9a10"
down_revision: str | Sequence[str] | None = "6943898d1be1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cameras",
        sa.Column(
            "analysed_fps",
            sa.Float(),
            nullable=True,
            comment="Frames per stream-second run through ANPR, as scheduled by the "
            "camera's tier (edge_agent.analytics.scheduler).",
        ),
    )
    op.add_column(
        "cameras",
        sa.Column(
            "analysis_lag_s",
            sa.Float(),
            nullable=True,
            comment="How far behind live the worker's analysis was at the last heartbeat: "
            "receipt time minus the stream position of the latest frame.",
        ),
    )
    op.add_column(
        "zone_events",
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="new",
            comment="new | acknowledged | resolved | false_positive",
        ),
    )
    op.add_column("zone_events", sa.Column("resolved_by", sa.String(), nullable=True))
    op.add_column(
        "zone_events",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_zone_events_status", "zone_events", ["status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_zone_events_status", table_name="zone_events")
    op.drop_column("zone_events", "updated_at")
    op.drop_column("zone_events", "resolved_by")
    op.drop_column("zone_events", "status")
    op.drop_column("cameras", "analysis_lag_s")
    op.drop_column("cameras", "analysed_fps")

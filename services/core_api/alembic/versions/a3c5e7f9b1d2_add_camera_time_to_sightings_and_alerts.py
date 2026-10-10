"""add the camera's burned-in clock to detections, zone events and alerts

Revision ID: a3c5e7f9b1d2
Revises: 9d4e6a2b7c31
Create Date: 2026-10-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c5e7f9b1d2"
down_revision: str | Sequence[str] | None = "9d4e6a2b7c31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Identical to the model comments, so autogenerate sees no drift.
_COLUMNS = (
    (
        "detections",
        "camera_time",
        "The clock burned into the evidence frame by the camera, confirmed by another "
        "reading of the same clock. The only time a sighting is reported with; NULL is time "
        "unknown. observed_at is processing time: ordering and partitioning only.",
    ),
    (
        "zone_events",
        "camera_time",
        "The clock burned into the frame that fired this event, confirmed by another "
        "reading of the same clock. NULL is time unknown; observed_at is processing time.",
    ),
    (
        "alerts",
        "first_seen_camera_time",
        "The camera's clock on the alert's earliest sighting. NULL is time unknown; "
        "first_seen_at is processing time, for deduplication only.",
    ),
    (
        "alerts",
        "last_seen_camera_time",
        "The camera's clock on the alert's latest sighting. NULL is time unknown; "
        "last_seen_at is processing time, for deduplication only.",
    ),
)


def upgrade() -> None:
    """Upgrade schema."""
    for table, column, comment in _COLUMNS:
        op.add_column(
            table,
            sa.Column(column, sa.DateTime(timezone=True), nullable=True, comment=comment),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table, column, _comment in reversed(_COLUMNS):
        op.drop_column(table, column)

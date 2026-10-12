"""index detections by camera, plate and camera time, for the duplicate check

Revision ID: c4e8a1d3f5b7
Revises: b7d2e4f6a8c0
Create Date: 2026-10-12 17:30:00.000000

Ingest refuses a read whose camera, plate and printed second are already
stored (a replayed buffer, a looping recording, a restarted worker). That
lookup runs on every detection, so it must not scan the hypertable.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a1d3f5b7"
down_revision: str | Sequence[str] | None = "b7d2e4f6a8c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_detections_camera_plate_camera_time",
        "detections",
        ["camera_id", "plate_normalised", "camera_time"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_detections_camera_plate_camera_time", table_name="detections")

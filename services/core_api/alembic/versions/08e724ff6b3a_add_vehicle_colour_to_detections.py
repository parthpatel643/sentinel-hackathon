"""add vehicle_colour to detections

Revision ID: 08e724ff6b3a
Revises: c882d80a41a6
Create Date: 2026-09-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "08e724ff6b3a"
down_revision: str | Sequence[str] | None = "c882d80a41a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "detections",
        sa.Column(
            "vehicle_colour",
            sa.String(),
            nullable=True,
            comment="M13 secondary analytics — a coarse HSV-heuristic classification, not a "
            "trained model. See edge_agent.analytics.colour.",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("detections", "vehicle_colour")

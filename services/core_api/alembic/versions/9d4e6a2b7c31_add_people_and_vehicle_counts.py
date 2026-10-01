"""add people and vehicle counts to cameras and object class to zone events

Revision ID: 9d4e6a2b7c31
Revises: 7b2c4e1f9a10
Create Date: 2026-10-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d4e6a2b7c31"
down_revision: str | Sequence[str] | None = "7b2c4e1f9a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cameras",
        sa.Column(
            "people_in_view",
            sa.Integer(),
            nullable=True,
            comment="Most people in one analysed frame since the previous heartbeat. A count, "
            "never an identity.",
        ),
    )
    op.add_column(
        "cameras",
        sa.Column(
            "vehicles_in_view",
            sa.Integer(),
            nullable=True,
            comment="Most vehicles in one analysed frame since the previous heartbeat.",
        ),
    )
    op.add_column(
        "zone_events",
        sa.Column(
            "object_class",
            sa.String(),
            nullable=False,
            server_default="vehicle",
            comment="vehicle | person",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("zone_events", "object_class")
    op.drop_column("cameras", "vehicles_in_view")
    op.drop_column("cameras", "people_in_view")

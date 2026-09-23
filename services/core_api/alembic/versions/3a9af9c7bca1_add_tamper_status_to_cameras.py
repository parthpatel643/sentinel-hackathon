"""add tamper_status to cameras

Revision ID: 3a9af9c7bca1
Revises: 08e724ff6b3a
Create Date: 2026-09-23 12:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a9af9c7bca1"
down_revision: str | Sequence[str] | None = "08e724ff6b3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cameras",
        sa.Column(
            "tamper_status",
            sa.String(),
            nullable=True,
            comment="M13 secondary analytics — 'ok' | 'covered' | 'blurred' | 'moved' | null "
            "(never reported yet). See edge_agent.analytics.tamper.",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cameras", "tamper_status")

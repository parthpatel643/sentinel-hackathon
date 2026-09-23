"""add hash-chained audit_log table

Revision ID: c882d80a41a6
Revises: 23c60ee4c006
Create Date: 2026-09-23 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c882d80a41a6"
down_revision: str | Sequence[str] | None = "23c60ee4c006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("actor_email", sa.String(), nullable=True),
        sa.Column(
            "action",
            sa.String(),
            nullable=False,
            comment="e.g. 'face_reveal', 'user_created', 'watchlist_entry_created', "
            "'retention_executed'",
        ),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prev_hash", sa.String(), nullable=False),
        sa.Column("row_hash", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_log_seq"), "audit_log", ["seq"], unique=True)
    op.create_index(op.f("ix_audit_log_row_hash"), "audit_log", ["row_hash"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_audit_log_row_hash"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_seq"), table_name="audit_log")
    op.drop_table("audit_log")

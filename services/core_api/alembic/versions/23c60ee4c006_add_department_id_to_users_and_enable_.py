"""add department_id to users and enable RLS department tenancy

Revision ID: 23c60ee4c006
Revises: bc2e193d6030
Create Date: 2026-09-23 09:32:57.966518

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "23c60ee4c006"
down_revision: str | Sequence[str] | None = "bc2e193d6030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# docs/08-SECURITY-HARDENING.md's department-tenancy RLS: NULL app.current_
# department_id (unset, or a user with no department of their own — the
# natural default for an HQ/admin account) means unrestricted; a set value
# scopes to that department's own cameras plus any camera with no
# department assigned yet (so the pre-M12 dev/demo grid, which nothing has
# ever assigned a department, stays visible to everyone rather than
# vanishing the moment RLS turns on).
_TENANCY_CLAUSE = (
    "current_setting('app.current_department_id', true) IS NULL "
    "OR current_setting('app.current_department_id', true) = '' "
    "OR department_id IS NULL "
    "OR department_id::text = current_setting('app.current_department_id', true)"
)
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
    op.add_column("users", sa.Column("department_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_users_department_id",
        "users",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )

    for table in ("cameras", "detections", "alerts"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE, not just ENABLE: without it, RLS is still skipped for the
        # table's OWNER (the `sentinel` migration role) — FORCE closes that
        # loophole too. Superusers remain unconditionally exempt regardless
        # (a hard Postgres rule, not a config knob) — that's exactly why
        # core_api's own connection now runs as the non-superuser
        # `sentinel_app` role (see sentinel_core.config.app_database_url).
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(
        f"CREATE POLICY department_tenancy ON cameras "
        f"USING ({_TENANCY_CLAUSE}) WITH CHECK ({_TENANCY_CLAUSE})"
    )
    for table in ("detections", "alerts"):
        op.execute(
            f"CREATE POLICY department_tenancy ON {table} "
            f"USING ({_CAMERA_JOIN_TENANCY_CLAUSE}) WITH CHECK ({_CAMERA_JOIN_TENANCY_CLAUSE})"
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("cameras", "detections", "alerts"):
        op.execute(f"DROP POLICY IF EXISTS department_tenancy ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_constraint("fk_users_department_id", "users", type_="foreignkey")
    op.drop_column("users", "department_id")

"""Baseline existing schema.

Use `alembic stamp 20260607_0001` on an existing database after taking a backup.
Fresh databases may continue to be initialized by the application, then stamped.
"""
revision = "20260607_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

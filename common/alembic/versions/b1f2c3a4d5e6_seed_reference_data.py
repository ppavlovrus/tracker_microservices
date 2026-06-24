"""Seed reference data (task statuses + default user)

Revision ID: b1f2c3a4d5e6
Revises: 07fe181d9152
Create Date: 2026-06-24 00:00:00.000000

Seeds the minimal rows the write-path depends on: task_status options and one
default user, so that POST /tasks (creator_id + status_id FKs) works out of the
box. Idempotent via ON CONFLICT DO NOTHING.

The default user's password_hash is a non-functional placeholder — auth is not
implemented yet, so this user cannot log in; it only satisfies the creator_id FK.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1f2c3a4d5e6'
down_revision: Union[str, Sequence[str], None] = '07fe181d9152'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert seed reference data."""
    op.execute(
        """
        INSERT INTO task_status (name) VALUES
            ('todo'),
            ('in_progress'),
            ('done')
        ON CONFLICT (name) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO "user" (username, email, password_hash) VALUES
            ('admin', 'admin@example.com', 'seed-placeholder-no-login')
        ON CONFLICT (username) DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove seed reference data."""
    op.execute("DELETE FROM \"user\" WHERE username = 'admin'")
    op.execute(
        "DELETE FROM task_status WHERE name IN ('todo', 'in_progress', 'done')"
    )

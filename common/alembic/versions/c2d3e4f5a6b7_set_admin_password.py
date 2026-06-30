"""Set a real bcrypt password for the default admin user

Revision ID: c2d3e4f5a6b7
Revises: b1f2c3a4d5e6
Create Date: 2026-06-30 00:00:00.000000

The seed migration created the ``admin`` user with a non-functional placeholder
hash. Now that login exists, replace it with a real bcrypt hash so the default
``admin`` / ``admin`` credentials work out of the box.

Idempotent: only the placeholder is replaced, so a manually changed password is
never clobbered by re-running migrations.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1f2c3a4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# bcrypt hash of the literal password "admin" (cost 12). A learning-project
# default credential -- change it in any real deployment.
_ADMIN_BCRYPT = '$2b$12$oOUmtFn7fm50bdt91.qyEelpY.SIYTtITMl8s4/O4evApDalGS.R2'
_PLACEHOLDER = 'seed-placeholder-no-login'


def upgrade() -> None:
    """Give the admin user a working bcrypt password."""
    op.execute(
        f"""
        UPDATE "user"
        SET password_hash = '{_ADMIN_BCRYPT}'
        WHERE username = 'admin' AND password_hash = '{_PLACEHOLDER}'
        """
    )


def downgrade() -> None:
    """Restore the non-functional placeholder hash."""
    op.execute(
        f"""
        UPDATE "user"
        SET password_hash = '{_PLACEHOLDER}'
        WHERE username = 'admin' AND password_hash = '{_ADMIN_BCRYPT}'
        """
    )

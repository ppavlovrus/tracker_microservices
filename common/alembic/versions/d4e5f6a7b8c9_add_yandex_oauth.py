"""Add Yandex OAuth support to the user table

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-07-12 00:00:00.000000

Users created via Yandex OAuth have no local password, so ``password_hash``
becomes nullable. ``yandex_id`` stores the immutable Yandex account id and is
the primary lookup key for OAuth logins; it is unique so one Yandex account
maps to at most one local user.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user.yandex_id and make password_hash optional."""
    op.add_column('user', sa.Column('yandex_id', sa.String(length=64), nullable=True))
    op.create_unique_constraint('uq_user_yandex_id', 'user', ['yandex_id'])
    op.alter_column('user', 'password_hash', existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    """Drop yandex_id and restore NOT NULL on password_hash."""
    # OAuth-only users have no password; give them a non-functional placeholder
    # so the NOT NULL constraint can be restored without failing.
    op.execute(
        """
        UPDATE "user"
        SET password_hash = 'seed-placeholder-no-login'
        WHERE password_hash IS NULL
        """
    )
    op.alter_column('user', 'password_hash', existing_type=sa.Text(), nullable=False)
    op.drop_constraint('uq_user_yandex_id', 'user', type_='unique')
    op.drop_column('user', 'yandex_id')

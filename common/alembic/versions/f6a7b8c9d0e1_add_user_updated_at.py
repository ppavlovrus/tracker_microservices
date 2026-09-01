"""Add the updated_at column the user queries have relied on all along

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-01 00:00:00.000000

The users repository selects and sets ``user.updated_at`` in every CRUD query,
but the initial schema never created the column -- the table got ``last_login``
instead. Every one of those queries has therefore failed at runtime since the
beginning ("column \"updated_at\" does not exist"), which took the whole
``/users`` CRUD down with a 500. Only the login lookups avoided the column, so
nobody noticed.

The column is added rather than removed from the queries because the public
API already promises it: ``UserResponse`` declares ``updated_at`` as required,
and the ``task`` table has carried the same column with the same semantics
since the initial schema.

Existing rows are backfilled with ``created_at``: the only query that writes
``updated_at`` -- the repository's dynamic UPDATE -- has never succeeded, so
creation time is the closest honest value on record. (Yandex-link updates did
touch some rows, but they never maintained ``updated_at`` either.)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user.updated_at: nullable first, backfill, then match task.updated_at."""
    op.add_column('user', sa.Column('updated_at', sa.TIMESTAMP(), nullable=True))
    op.execute('UPDATE "user" SET updated_at = created_at')
    op.alter_column(
        'user',
        'updated_at',
        nullable=False,
        server_default=sa.text('now()'),
    )


def downgrade() -> None:
    """Drop user.updated_at."""
    op.drop_column('user', 'updated_at')

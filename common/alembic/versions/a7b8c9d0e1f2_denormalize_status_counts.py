"""Denormalize the per-status task counts into a counter table

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-06 00:00:00.000000

The Kanban column totals come from ``count(*) FILTER`` aggregates over the
whole task table -- an O(n) pass on every board load, while the counts only
actually change when a task is created, deleted or moved between statuses.
This table stores one counter per status; the task repository maintains it on
those three write paths, inside the same transaction as the task row, and the
stats query becomes an O(1) read of a handful of rows.

The CHECK constraint is deliberate: the counters cannot drift under normal
operation (the updates are transactional with the row changes), so the ways
left to drift are bugs or manual edits behind the application's back. A
negative counter is proof of one, and failing the offending decrement loudly
beats serving a quietly wrong board forever.

The backfill seeds one row per status via LEFT JOIN, so a status with no
tasks gets an explicit zero and keeps appearing in the stats response.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create task_status_count and backfill it from the current task rows."""
    op.create_table(
        'task_status_count',
        sa.Column(
            'status_id',
            sa.Integer(),
            sa.ForeignKey('task_status.id', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column('cnt', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint('cnt >= 0', name='ck_task_status_count_nonnegative'),
    )
    op.execute(
        """
        INSERT INTO task_status_count (status_id, cnt)
        SELECT s.id, count(t.id)
        FROM task_status s
        LEFT JOIN task t ON t.status_id = s.id
        GROUP BY s.id
        """
    )


def downgrade() -> None:
    """Drop the counter table; the FILTER aggregates can always recompute it."""
    op.drop_table('task_status_count')

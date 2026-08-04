"""Add indexes for existing hot-path queries

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-04 00:00:00.000000

The initial schema created only the implicit indexes behind primary keys and
unique constraints. PostgreSQL does *not* index foreign keys automatically, so
every FK join and every ORDER BY here was a sequential scan. Each index below
is added for a query that already exists in the code, not speculatively:

* task.created_at   -- list_tasks: ORDER BY created_at DESC LIMIT/OFFSET
                       (a plain b-tree is read backwards for DESC ordering)
* task.creator_id   -- FK; DELETE "user" (ondelete RESTRICT) must scan children
* task.status_id    -- FK; status filtering / FILTER counters
* task_tag.tag_id   -- reverse side of the M2M; the PK (task_id, tag_id) only
                       serves the left prefix, so "tasks for tag X" and the
                       tag JOIN on tag.id had no usable index
* comment.task_id   -- comments listed by task_id; FK
* attachment.task_id-- attachments listed by task_id; FK
* auth_session.user_id -- FK; "last login per user" lookups

No composite (creator_id, created_at) index is added: no query filters by
creator and sorts by created_at at the same time yet.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create indexes for existing FK joins and ORDER BY clauses."""
    op.create_index('idx_task_created_at', 'task', ['created_at'])
    op.create_index('idx_task_creator_id', 'task', ['creator_id'])
    op.create_index('idx_task_status_id', 'task', ['status_id'])
    op.create_index('idx_task_tag_tag_id', 'task_tag', ['tag_id'])
    op.create_index('idx_comment_task_id', 'comment', ['task_id'])
    op.create_index('idx_attachment_task_id', 'attachment', ['task_id'])
    op.create_index('idx_auth_session_user_id', 'auth_session', ['user_id'])


def downgrade() -> None:
    """Drop the indexes created in upgrade()."""
    op.drop_index('idx_auth_session_user_id', table_name='auth_session')
    op.drop_index('idx_attachment_task_id', table_name='attachment')
    op.drop_index('idx_comment_task_id', table_name='comment')
    op.drop_index('idx_task_tag_tag_id', table_name='task_tag')
    op.drop_index('idx_task_status_id', table_name='task')
    op.drop_index('idx_task_creator_id', table_name='task')
    op.drop_index('idx_task_created_at', table_name='task')

"""Task repository for database operations."""

import json
import logging
from datetime import datetime
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Columns selected for a task, aliased to the ``task`` table so they stay
# unambiguous once we LEFT JOIN task_tag/tag to aggregate the tags.
_TASK_COLUMNS = """
    t.id, t.title, t.description, t.status_id, t.creator_id,
    t.deadline_start, t.deadline_end, t.created_at, t.updated_at
"""

# Aggregate a task's tags into a JSON array in the same query (no N+1).
#   - ORDER BY inside the aggregate -> stable tag order
#   - FILTER (WHERE tg.id IS NOT NULL) -> a task with no tags yields [] and not
#     [null], which a bare LEFT JOIN + json_agg would produce
#   - COALESCE(..., '[]') -> json_agg returns NULL (not []) on an empty group
_TAGS_AGG = """
    COALESCE(
        json_agg(json_build_object('id', tg.id, 'name', tg.name) ORDER BY tg.name)
            FILTER (WHERE tg.id IS NOT NULL),
        '[]'
    ) AS tags
"""


class TaskRepository:
    """Repository for Task entity operations."""

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize TaskRepository.

        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool

    @staticmethod
    def _row_to_task(row: asyncpg.Record) -> dict[str, Any]:
        """Turn a task row into a dict, decoding the aggregated ``tags`` column.

        asyncpg returns ``json`` columns as raw strings unless a type codec is
        registered, so the ``json_agg`` result arrives as text and must be
        parsed back into a list.
        """
        task = dict(row)
        tags = task.get("tags")
        if isinstance(tags, str):
            task["tags"] = json.loads(tags)
        return task

    @staticmethod
    async def _bump_status_counts(conn: asyncpg.Connection, deltas: dict[int, int]) -> None:
        """Apply per-status counter deltas inside the caller's transaction.

        Statuses are processed in ascending order so that two transactions
        moving tasks between the same pair of statuses in opposite directions
        lock the counter rows in the same order and cannot deadlock. The
        upsert covers a status added after the backfill migration: its first
        task inserts the row.
        """
        for status_id in sorted(deltas):
            delta = deltas[status_id]
            if delta == 0:
                continue
            if delta > 0:
                await conn.execute(
                    """
                    INSERT INTO task_status_count AS c (status_id, cnt)
                    VALUES ($1, $2)
                    ON CONFLICT (status_id) DO UPDATE SET cnt = c.cnt + $2
                    """,
                    status_id,
                    delta,
                )
            else:
                # Not the same upsert with a negative delta: Postgres checks the
                # candidate INSERT row against the table's CHECK constraints
                # BEFORE resolving the conflict, so VALUES ($1, -1) violates
                # cnt >= 0 even when the existing row would absorb it. A plain
                # UPDATE is also honest about drift: decrementing a status that
                # has no counter row means some earlier write path failed to
                # maintain it, and that deserves a loud record, not a new row.
                result = await conn.execute(
                    "UPDATE task_status_count SET cnt = cnt + $2 WHERE status_id = $1",
                    status_id,
                    delta,
                )
                if result != "UPDATE 1":
                    logger.error(f"No counter row for status {status_id}; counters have drifted")

    async def get_by_id(self, task_id: int) -> dict[str, Any] | None:
        """
        Get task by ID, with its tags aggregated in the same query.

        Args:
            task_id: Task ID

        Returns:
            Task data (including a ``tags`` list) as dict or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_TASK_COLUMNS}, {_TAGS_AGG}
                FROM task t
                LEFT JOIN task_tag tt ON tt.task_id = t.id
                LEFT JOIN tag tg ON tg.id = tt.tag_id
                WHERE t.id = $1
                GROUP BY t.id
                """,
                task_id,
            )
            return self._row_to_task(row) if row else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create new task.

        Args:
            data: Task data (title, description, creator_id, status_id, deadlines)

        Returns:
            Created task data
        """
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO task (
                    title, description, status_id, creator_id,
                    deadline_start, deadline_end
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, title, description, status_id, creator_id,
                          deadline_start, deadline_end, created_at, updated_at
                """,
                data.get("title"),
                data.get("description"),
                data.get("status_id", 1),  # Default status
                data.get("creator_id"),
                data.get("deadline_start"),
                data.get("deadline_end"),
            )
            await self._bump_status_counts(conn, {row["status_id"]: 1})

            logger.info(f"Task created: ID={row['id']}, title='{row['title']}'")
            return dict(row)

    async def update(self, task_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Update task by ID.

        Args:
            task_id: Task ID
            data: Fields to update

        Returns:
            Updated task data or None if not found
        """
        # Build dynamic UPDATE query for provided fields only
        set_clauses = []
        values = []
        param_index = 1

        for field in ["title", "description", "status_id", "deadline_start", "deadline_end"]:
            if field in data:
                set_clauses.append(f"{field} = ${param_index}")
                values.append(data[field])
                param_index += 1

        if not set_clauses:
            # No fields to update, just return current task
            return await self.get_by_id(task_id)

        # Add updated_at
        set_clauses.append(f"updated_at = ${param_index}")
        values.append(datetime.utcnow())
        param_index += 1

        # Add task_id for WHERE clause
        values.append(task_id)

        query = f"""
            UPDATE task
            SET {", ".join(set_clauses)}
            WHERE id = ${param_index}
            RETURNING id, title, description, status_id, creator_id,
                      deadline_start, deadline_end, created_at, updated_at
        """

        async with self.pool.acquire() as conn, conn.transaction():
            old_status = None
            if "status_id" in data:
                # The counters need the pre-update status, and RETURNING only
                # sees the new row. FOR UPDATE holds the row so a concurrent
                # status change cannot slip in between this read and the write.
                old_status = await conn.fetchval("SELECT status_id FROM task WHERE id = $1 FOR UPDATE", task_id)
                if old_status is None:
                    logger.warning(f"Task not found for update: ID={task_id}")
                    return None

            row = await conn.fetchrow(query, *values)

            if row is None:
                logger.warning(f"Task not found for update: ID={task_id}")
                return None

            if old_status is not None and row["status_id"] != old_status:
                await self._bump_status_counts(conn, {old_status: -1, row["status_id"]: 1})

            logger.info(f"Task updated: ID={task_id}")
            return dict(row)

    async def delete(self, task_id: int) -> bool:
        """
        Delete task by ID.

        Args:
            task_id: Task ID

        Returns:
            True if deleted, False if not found
        """
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow("DELETE FROM task WHERE id = $1 RETURNING status_id", task_id)

            if row is None:
                logger.warning(f"Task not found for deletion: ID={task_id}")
                return False

            await self._bump_status_counts(conn, {row["status_id"]: -1})
            logger.info(f"Task deleted: ID={task_id}")
            return True

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """
        Get all tasks with pagination.

        Args:
            limit: Maximum number of tasks to return
            offset: Number of tasks to skip

        Returns:
            List of tasks
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_TASK_COLUMNS}, {_TAGS_AGG}
                FROM task t
                LEFT JOIN task_tag tt ON tt.task_id = t.id
                LEFT JOIN tag tg ON tg.id = tt.tag_id
                GROUP BY t.id
                ORDER BY t.created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
            return [self._row_to_task(row) for row in rows]

    async def count_all(self) -> int:
        """
        Count total number of tasks.

        Returns:
            Total count
        """
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM task")
            return count or 0

    async def count_by_status(self) -> dict[str, int]:
        """Read the denormalized per-status counters.

        These used to be ``count(*) FILTER`` aggregates over the whole task
        table — an O(n) pass on every board load. The counters are now
        maintained by the write paths (create, delete, status change) in the
        same transaction as the task row, so this reads a handful of rows
        regardless of table size. The backfill migration seeded a zero row per
        status, so every status stays present in the answer.

        Returns a dict keyed by status id (as string, for JSON transport) plus a
        ``total`` key.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT status_id, cnt FROM task_status_count ORDER BY status_id")

        counts: dict[str, int] = {"total": 0}
        for row in rows:
            counts[str(row["status_id"])] = row["cnt"]
            counts["total"] += row["cnt"]
        return counts

    async def add_tag(self, task_id: int, tag_id: int) -> None:
        """Link a tag to a task (idempotent)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO task_tag (task_id, tag_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                task_id,
                tag_id,
            )

    async def remove_tag(self, task_id: int, tag_id: int) -> bool:
        """Unlink a tag from a task. Returns True if a row was removed."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM task_tag WHERE task_id = $1 AND tag_id = $2",
                task_id,
                tag_id,
            )
            return result.split()[-1] == "1"

    async def get_tags_for_tasks(self, task_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        """Return ``{task_id: [{id, name}, ...]}`` for the given task ids.

        Done in a single query to avoid an N+1 when listing the board.
        """
        if not task_ids:
            return {}
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT tt.task_id, t.id, t.name
                FROM task_tag tt
                JOIN tag t ON t.id = tt.tag_id
                WHERE tt.task_id = ANY($1::int[])
                ORDER BY t.name
                """,
                task_ids,
            )
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["task_id"], []).append({"id": row["id"], "name": row["name"]})
        return grouped

    async def get_tags_for_task(self, task_id: int) -> list[dict[str, Any]]:
        """Return the list of ``{id, name}`` tags linked to one task."""
        return (await self.get_tags_for_tasks([task_id])).get(task_id, [])

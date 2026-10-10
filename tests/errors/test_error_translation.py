"""What a worker failure turns into by the time a client sees it.

Two things used to go wrong here and neither is visible from a schema. A
foreign-key violation escaped unclassified, so a task naming a creator nobody
answers to came back as a 500. And an unclassified failure answered with
``str(exc)``, which for a driver error is the table, the constraint name and
the offending value -- handed to whoever made the request.

The translations are pure functions and tables, so these run without a stack.
"""

import asyncpg
import pytest
import tracker_attachments.handlers.attachment_handlers as attachments
import tracker_comments.handlers.comment_handlers as comments
import tracker_tags.handlers.tag_handlers as tags
import tracker_tasks.handlers.task_handlers as tasks
from fastapi import HTTPException
from task_tracker_common.contracts.responses import ErrorCode
from tracker_gateway.api.errors import STATUS
from tracker_gateway.api.routers._rpc import STATUS_BY_CODE, call_worker
from tracker_gateway.broker.tasks_client import MISSING_REFERENCE
from tracker_gateway.core.exceptions import (
    BusProtocolError,
    CreatorNotFoundError,
    StatusNotFoundError,
    UpstreamFailureError,
)


def fk_violation(constraint: str) -> asyncpg.ForeignKeyViolationError:
    """A real driver error, carrying the constraint name the server reports."""
    return asyncpg.exceptions.ForeignKeyViolationError.new(
        {
            "C": "23503",
            "M": (
                f'insert or update on table "comment" violates foreign key constraint "{constraint}"'
                "\nDETAIL:  Key (task_id)=(999999999) is not present in table \"task\"."
            ),
            "n": constraint,
        }
    )


# -- a missing reference is the caller's problem, not an internal failure ---


@pytest.mark.parametrize(
    ("constraint", "field", "message"),
    [
        ("task_creator_id_fkey", "creator_id", "Creator not found"),
        ("task_status_id_fkey", "status_id", "Status not found"),
    ],
)
def test_tasks_names_the_column_that_pointed_nowhere(constraint, field, message):
    answer = tasks._missing_reference(fk_violation(constraint))

    assert answer["success"] is False
    assert answer["code"] == ErrorCode.NOT_FOUND
    assert answer["error"] == message
    # The machine-readable half: the gateway picks a domain error from this
    # rather than parsing the message.
    assert answer["error_type"] == field


@pytest.mark.parametrize(
    ("constraint", "field", "message"),
    [
        ("comment_task_id_fkey", "task_id", "Task not found"),
        ("comment_user_id_fkey", "user_id", "User not found"),
    ],
)
def test_comments_names_the_column_that_pointed_nowhere(constraint, field, message):
    answer = comments._missing_reference(fk_violation(constraint))

    assert answer["code"] == ErrorCode.NOT_FOUND
    assert answer["error"] == message
    assert answer["error_type"] == field


def test_attachments_reports_a_missing_task():
    answer = attachments._missing_reference(fk_violation("attachment_task_id_fkey"))

    assert answer["code"] == ErrorCode.NOT_FOUND
    assert answer["error"] == "Task not found"


# -- an unclassified failure says nothing about the database ----------------


@pytest.mark.parametrize(
    "module",
    [attachments],
    ids=["attachments"],
)
def test_an_unclassified_failure_carries_no_driver_text(module):
    """This one answers a router that puts ``error`` straight into the body."""
    answer = module._internal(fk_violation("comment_task_id_fkey"))

    assert answer["code"] == ErrorCode.INTERNAL
    assert answer["error"] == "Internal error"
    # Nothing the server said about its own schema travels with it.
    for leaked in ("constraint", "violates", "DETAIL", "999999999", "comment_task_id_fkey"):
        assert leaked not in str(answer), f"{leaked!r} reached the answer"


def test_tags_reports_a_taken_name_as_a_conflict():
    """The tags worker no longer pre-checks uniqueness: the constraint decides."""
    exc = asyncpg.UniqueViolationError.new(
        {
            "C": "23505",
            "M": 'duplicate key value violates unique constraint "tag_name_key"',
            "n": "tag_name_key",
        }
    )

    answer = tags._conflict(exc)

    assert answer["code"] == ErrorCode.CONFLICT
    assert answer["error"] == "Tag with this name already exists"
    assert answer["error_type"] == "name"


def test_the_typed_verticals_are_covered_by_the_status_table_instead():
    """Tasks, users, tags and comments do send the driver text, and it stops at the gateway.

    Their dispatchers put ``str(exc)`` in the envelope on purpose -- it is the
    operator's half of the story and belongs in the gateway's log. What the
    client is told comes from this table and never from the worker, which is
    why those verticals need no ``_internal`` of their own.
    """
    assert STATUS[UpstreamFailureError] == (500, "Internal server error")
    assert STATUS[BusProtocolError] == (500, "Internal server error")


# -- and the gateway turns the codes into the statuses they deserve ---------


def test_a_named_column_becomes_a_400_about_the_request():
    """Not a 404: the addressed resource is fine, the reference inside is not."""
    assert MISSING_REFERENCE["creator_id"] is CreatorNotFoundError
    assert MISSING_REFERENCE["status_id"] is StatusNotFoundError
    assert STATUS[CreatorNotFoundError] == (400, "Unknown creator_id")
    assert STATUS[StatusNotFoundError] == (400, "Unknown status_id")


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (ErrorCode.NOT_FOUND, 404),
        (ErrorCode.VALIDATION_ERROR, 400),
        (ErrorCode.CONFLICT, 409),
        (ErrorCode.INTERNAL, 500),
    ],
)
def test_raw_routers_take_the_status_from_the_code(code, status):
    assert STATUS_BY_CODE[code] == status


def test_an_answer_without_a_code_leaves_the_endpoint_in_charge():
    """Workers that cannot classify a failure still answer; the endpoint decides."""
    assert STATUS_BY_CODE.get(None, 418) == 418


class _StubClient:
    """A bus client answering one canned envelope."""

    def __init__(self, envelope: dict):
        self._envelope = envelope

    async def call(self, *, queue_name, message, timeout):
        return self._envelope


async def test_a_raw_router_hides_an_unclassified_workers_text():
    """A typed dispatcher puts the driver's words in ``error`` on purpose.

    Until every vertical has a typed client, the raw router is the last stop
    before the client: the words land in the log, never in the HTTP body.
    """
    driver_words = 'connection refused: postgres@db:5432 "task"'
    stub = _StubClient({"success": False, "code": ErrorCode.INTERNAL, "error": driver_words})

    with pytest.raises(HTTPException) as exc:
        await call_worker(
            stub,
            queue="tags.commands",
            service="Tags",
            command="list_tags",
            data={"limit": 1, "offset": 0},
            timeout=5.0,
            failure_status=500,
            failure_detail="Unknown error",
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == "Internal server error"

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
import tracker_users.handlers.user_handlers as users
from task_tracker_common.contracts.responses import ErrorCode
from tracker_gateway.api.errors import STATUS
from tracker_gateway.broker.tags_client import TagsBusClient
from tracker_gateway.broker.tasks_client import MISSING_REFERENCE
from tracker_gateway.core.exceptions import (
    BusProtocolError,
    CreatorNotFoundError,
    SessionStoreUnavailableError,
    StatusNotFoundError,
    UpstreamFailureError,
    UserHasTasksError,
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
#
# The last ``_internal`` helper went with the attachments refactor: every
# worker now answers through the shared dispatcher, whose INTERNAL envelope
# stops at the gateway (see the stub test at the bottom of this file).


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
    """Every worker's dispatcher sends the driver text, and it stops at the gateway.

    The dispatchers put ``str(exc)`` in the envelope on purpose -- it is the
    operator's half of the story and belongs in the gateway's log. What the
    client is told comes from this table and never from the worker, which is
    why no vertical needs an ``_internal`` of its own.
    """
    assert STATUS[UpstreamFailureError] == (500, "Internal server error")
    assert STATUS[BusProtocolError] == (500, "Internal server error")


def test_a_login_without_its_session_backend_refuses_to_start():
    """No store -> no CSRF state, no session: one 503 wording for both causes.

    The old router answered two wordings here ("Service temporarily
    unavailable" for a missing store, "Session backend unavailable" for a
    down Redis); the service owns the flow now and refuses it one way.
    """
    assert STATUS[SessionStoreUnavailableError] == (503, "Session backend unavailable")


# -- and the gateway turns the codes into the statuses they deserve ---------


def test_a_named_column_becomes_a_400_about_the_request():
    """Not a 404: the addressed resource is fine, the reference inside is not."""
    assert MISSING_REFERENCE["creator_id"] is CreatorNotFoundError
    assert MISSING_REFERENCE["status_id"] is StatusNotFoundError
    assert STATUS[CreatorNotFoundError] == (400, "Unknown creator_id")
    assert STATUS[StatusNotFoundError] == (400, "Unknown status_id")


def test_a_user_deletion_blocked_by_tasks_becomes_a_409():
    """The only reference that blocks a user deletion is a task naming them
    creator (comments and attachments cascade); the conflict says so."""
    answer = users._still_referenced()

    assert answer["code"] == ErrorCode.CONFLICT
    assert answer["error"] == "User still has tasks"
    assert answer["error_type"] == "tasks"
    assert STATUS[UserHasTasksError] == (409, "User still has tasks")


class _StubBus:
    """A RabbitMQ client answering one canned envelope."""

    def __init__(self, envelope: dict):
        self._envelope = envelope

    async def call(self, *, queue_name, message, timeout):
        return self._envelope


async def test_a_typed_client_hides_the_workers_internal_text():
    """A dispatcher puts the driver's words in ``error`` on purpose.

    The typed client turns INTERNAL into UpstreamFailureError and the words
    stop in its log: what the HTTP client is told comes from the status
    table, never from the worker.
    """
    driver_words = 'connection refused: postgres@db:5432 "tag"'
    client = TagsBusClient(_StubBus({"success": False, "code": ErrorCode.INTERNAL, "error": driver_words}))

    with pytest.raises(UpstreamFailureError) as exc:
        await client.get(1)

    assert STATUS[UpstreamFailureError] == (500, "Internal server error")
    assert driver_words not in str(exc.value)

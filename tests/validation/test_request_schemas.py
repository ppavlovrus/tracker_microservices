"""What the request schemas refuse, and why.

Every case here used to reach the database and come back as a 500 or, worse,
as a driver error carrying the constraint's name. The rule under test is not
"pydantic works" -- it is that a request the schema in question cannot satisfy
is refused before it costs a round trip, and that a legitimate partial update
still goes through untouched.

No stack needed: these are the models, not the endpoints.
"""

import pytest
from _pytest._code import ExceptionInfo
from pydantic import ValidationError
from task_tracker_common.contracts.base import INT4_MAX, INT8_MAX, MAX_FREE_TEXT
from task_tracker_common.contracts.commands import (
    TagCreationContract,
    TagGetByIdContract,
    TagListContract,
    TaskCreationContract,
    TaskUpdatePayloadContract,
)
from tracker_gateway.api.schemas.attachment import AttachmentCreate
from tracker_gateway.api.schemas.comment import CommentCreate, CommentUpdate
from tracker_gateway.api.schemas.tags import TagCreate, TagUpdate
from tracker_gateway.api.schemas.task import TaskCreate, TaskUpdate
from tracker_gateway.api.schemas.user import UserUpdate


def field_of(exc: ExceptionInfo[ValidationError]) -> tuple:
    """The location the first error points at, which is what a 422 shows."""
    return exc.value.errors()[0]["loc"]


# -- task status: a dictionary table, not an open integer ------------------


@pytest.mark.parametrize("status_id", [0, -1, 4, 999, INT4_MAX])
def test_create_rejects_status_outside_the_dictionary(status_id):
    with pytest.raises(ValidationError) as exc:
        TaskCreate(title="t", creator_id=1, status_id=status_id)
    assert field_of(exc) == ("status_id",)


@pytest.mark.parametrize("status_id", [1, 2, 3])
def test_create_accepts_every_seeded_status(status_id):
    assert TaskCreate(title="t", creator_id=1, status_id=status_id).status_id == status_id


def test_create_defaults_to_todo():
    assert TaskCreate(title="t", creator_id=1).status_id == 1


def test_update_rejects_status_outside_the_dictionary():
    with pytest.raises(ValidationError) as exc:
        TaskUpdate(status_id=999)
    assert field_of(exc) == ("status_id",)


def test_bus_contract_rejects_status_outside_the_dictionary():
    """The worker's own contract holds the same line, not just the gateway."""
    with pytest.raises(ValidationError):
        TaskCreationContract(
            title="t",
            description=None,
            status_id=999,
            creator_id=1,
            deadline_start=None,
            deadline_end=None,
        )


# -- ids: shaped like a key, or refused ------------------------------------


@pytest.mark.parametrize("creator_id", [0, -1, INT4_MAX + 1, 3_000_000_000])
def test_create_rejects_unusable_creator_id(creator_id):
    with pytest.raises(ValidationError) as exc:
        TaskCreate(title="t", creator_id=creator_id)
    assert field_of(exc) == ("creator_id",)


def test_create_accepts_the_largest_storable_id():
    assert TaskCreate(title="t", creator_id=INT4_MAX).creator_id == INT4_MAX


@pytest.mark.parametrize("bad", [0, -7, INT4_MAX + 1])
def test_comment_rejects_unusable_task_id(bad):
    with pytest.raises(ValidationError) as exc:
        CommentCreate(task_id=bad, user_id=1, content="x")
    assert field_of(exc) == ("task_id",)


@pytest.mark.parametrize("bad", [0, -7, INT4_MAX + 1])
def test_comment_rejects_unusable_user_id(bad):
    with pytest.raises(ValidationError) as exc:
        CommentCreate(task_id=1, user_id=bad, content="x")
    assert field_of(exc) == ("user_id",)


def test_attachment_rejects_unusable_task_id():
    with pytest.raises(ValidationError) as exc:
        AttachmentCreate(task_id=0, filename="f.txt")
    assert field_of(exc) == ("task_id",)


def test_attachment_rejects_a_size_the_column_cannot_hold():
    with pytest.raises(ValidationError) as exc:
        AttachmentCreate(task_id=1, filename="f.txt", size_bytes=INT8_MAX + 1)
    assert field_of(exc) == ("size_bytes",)


# -- free text: unlimited in Postgres, bounded here ------------------------


def test_description_is_capped():
    with pytest.raises(ValidationError) as exc:
        TaskCreate(title="t", creator_id=1, description="x" * (MAX_FREE_TEXT + 1))
    assert field_of(exc) == ("description",)


def test_description_at_the_cap_is_allowed():
    assert len(TaskCreate(title="t", creator_id=1, description="x" * MAX_FREE_TEXT).description) == MAX_FREE_TEXT


def test_comment_content_is_capped():
    with pytest.raises(ValidationError) as exc:
        CommentCreate(task_id=1, user_id=1, content="y" * (MAX_FREE_TEXT + 1))
    assert field_of(exc) == ("content",)


def test_comment_update_content_is_capped():
    with pytest.raises(ValidationError) as exc:
        CommentUpdate(content="y" * (MAX_FREE_TEXT + 1))
    assert field_of(exc) == ("content",)


# -- partial updates: absent means "leave alone", null means "blank it" ----


@pytest.mark.parametrize("model", [TaskUpdate, UserUpdate])
def test_an_update_naming_nothing_is_refused(model):
    """The workers answer an empty update with a validation error -> a 500."""
    with pytest.raises(ValidationError) as exc:
        model()
    assert "at least one field" in exc.value.errors()[0]["msg"]


@pytest.mark.parametrize("field", ["title", "status_id"])
def test_task_update_refuses_to_blank_a_not_null_column(field):
    with pytest.raises(ValidationError) as exc:
        TaskUpdate(**{field: None})
    assert field_of(exc) == (field,)


@pytest.mark.parametrize("field", ["username", "email", "password"])
def test_user_update_refuses_to_blank_a_not_null_column(field):
    with pytest.raises(ValidationError) as exc:
        UserUpdate(**{field: None})
    assert field_of(exc) == (field,)


@pytest.mark.parametrize("field", ["description", "deadline_start", "deadline_end"])
def test_task_update_still_clears_a_nullable_column(field):
    """Clearing these is a legitimate edit and must keep working."""
    update = TaskUpdate(**{field: None})
    assert field in update.model_fields_set
    assert getattr(update, field) is None


def test_a_partial_update_touches_only_what_it_names():
    update = TaskUpdate(title="new")
    assert update.model_fields_set == {"title"}
    assert update.model_dump(exclude_unset=True) == {"title": "new"}


# -- the rule that was already there, kept under test ----------------------


def test_deadline_end_before_start_is_refused():
    with pytest.raises(ValidationError) as exc:
        TaskCreate(
            title="t",
            creator_id=1,
            deadline_start="2027-06-01",
            deadline_end="2027-01-01",
        )
    assert field_of(exc) == ("deadline_end",)


def test_deadline_end_after_start_is_allowed():
    task = TaskCreate(title="t", creator_id=1, deadline_start="2027-01-01", deadline_end="2027-06-01")
    assert task.deadline_end.isoformat() == "2027-06-01"


def test_bus_update_contract_keeps_the_deadline_rule():
    with pytest.raises(ValidationError):
        TaskUpdatePayloadContract(deadline_start="2027-06-01", deadline_end="2027-01-01")


# -- tags: a name is the whole tag -----------------------------------------


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_tag_rejects_a_name_the_column_cannot_hold(name):
    with pytest.raises(ValidationError) as exc:
        TagCreate(name=name)
    assert field_of(exc) == ("name",)


def test_tag_name_at_the_cap_is_allowed():
    assert len(TagCreate(name="x" * 100).name) == 100


def test_tag_update_requires_a_name():
    """A tag update is a rename, not a partial edit: naming nothing is refused."""
    with pytest.raises(ValidationError) as exc:
        TagUpdate()
    assert field_of(exc) == ("name",)


def test_tag_bus_creation_contract_holds_the_same_name_line():
    with pytest.raises(ValidationError):
        TagCreationContract(name="x" * 101)


@pytest.mark.parametrize("bad", [0, -7, INT4_MAX + 1])
def test_tag_bus_contract_rejects_unusable_id(bad):
    with pytest.raises(ValidationError):
        TagGetByIdContract(id=bad)


@pytest.mark.parametrize(
    "page",
    [{"limit": 0, "offset": 0}, {"limit": 101, "offset": 0}, {"limit": 1, "offset": -1}],
)
def test_tag_bus_list_contract_bounds_the_page(page):
    with pytest.raises(ValidationError):
        TagListContract(**page)

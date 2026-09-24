from enum import IntEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    """Base for bus contracts: an unexpected field is a contract change."""

    model_config = ConfigDict(extra="forbid")


# Every id in the schema is a Postgres int4. A request for an id past this is
# not "not found" -- it cannot exist, and asking the database costs a round
# trip that ends in a driver error rather than an answer.
INT4_MAX = 2_147_483_647

# A primary key or foreign key, as far as a schema can judge one: positive and
# inside int4. Existence is the database's business; shape is ours, and asking
# it here is what keeps a zero or a 3-billion id from reaching the driver.
RowId = Annotated[int, Field(gt=0, le=INT4_MAX)]

# ``attachment.size_bytes`` is a bigint. Same reasoning as the ids: a number
# past this is not a large file, it is a value the column cannot hold.
INT8_MAX = 9_223_372_036_854_775_807


class TaskStatusId(IntEnum):
    """The ids seeded into ``task_status`` by migration b1f2c3a4d5e6.

    ``task.status_id`` is a foreign key with ``ondelete=RESTRICT``, so a value
    outside this dictionary is not a 500 waiting to happen -- it is a request
    that cannot be satisfied, and it is cheaper to say so before the bus.

    Inputs are validated against this enum; answers are plain ints. A status
    added by a later migration must be added here (and to ``count_by_status``
    in the tasks repository and to ``STATUSES`` in the web UI), but until then
    it can still be read back without failing validation on the way out.
    """

    TODO = 1
    IN_PROGRESS = 2
    DONE = 3


# Descriptions and comment bodies are Postgres ``text``, which has no length
# limit of its own. This cap does not mirror a column -- it exists so a single
# request cannot park an unbounded string in the database.
MAX_FREE_TEXT = 10_000

# The str half of a nullable free-text column. Written as an annotated str
# rather than ``str | None = Field(max_length=...)`` so the bound lands on the
# string itself and a null still passes where the column allows one.
FreeText = Annotated[str, Field(max_length=MAX_FREE_TEXT)]

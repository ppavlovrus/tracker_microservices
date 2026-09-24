"""Building blocks for partial-update bodies (PUT with a subset of fields).

Two rules a plain optional field cannot express on its own, and both of them
currently end as a 500 rather than a 422:

* a body that names no field at all is not an empty update -- the tasks and
  users workers reject it as a validation error, which reaches the client as
  an internal server error;
* naming a field and setting it to ``null`` asks to write NULL into a column
  the database declares NOT NULL, and that fails at the driver.

Caught here instead, so the caller gets a 422 that names the field.
"""

from typing import Any

from pydantic import BaseModel, model_validator


def reject_null(value: Any) -> Any:
    """Refuse an explicit null for a column the database declares NOT NULL.

    Pydantic runs a field validator only for a field the caller actually sent,
    so arriving here with ``None`` means the body carried an explicit null
    rather than leaving the field out. Leaving it out is how a partial update
    says "do not touch this column", and that still works.
    """
    if value is None:
        raise ValueError("must not be null")
    return value


class PartialUpdate(BaseModel):
    """A body that has to name at least one field to be an update at all."""

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "PartialUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self

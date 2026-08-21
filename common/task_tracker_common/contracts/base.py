from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Base for bus contracts: an unexpected field is a contract change."""

    model_config = ConfigDict(extra="forbid")

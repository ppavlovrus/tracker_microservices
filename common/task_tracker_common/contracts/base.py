from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Base for bus contracts: an unexpected field is a contract change."""

    model_config = ConfigDict(extra="forbid")


# Every id in the schema is a Postgres int4. A request for an id past this is
# not "not found" -- it cannot exist, and asking the database costs a round
# trip that ends in a driver error rather than an answer.
INT4_MAX = 2_147_483_647

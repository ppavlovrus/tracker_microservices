from pydantic import BaseModel, Field


class Record(BaseModel):
    record_type: str = Field(..., min_length=1, max_length=255)
    record_owner: str = Field(..., min_length=1, max_length=255)
    amount: int = Field(..., ge=0)

class Response(BaseModel):
    status: str
    error: str = None
    message: str = None
    record: Record = None

class RecordListResponse(BaseModel):
    status: str
    message: str = None
    error: str = None
    records: list[Record] = []
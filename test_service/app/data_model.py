from pydantic import BaseModel, Field
from datetime import date

class ModelRecord(BaseModel):
    id: int | None = None
    record_type: str = Field(..., min_length=1, max_length=255)
    record_owner: str = Field(..., min_length=1, max_length=255)
    amount: int = Field(..., ge=0)

    def remove_fee_from_amount(self):
        self.amount = int(self.amount - self.amount * 0.13)

    def add_date_to_record(self):
        self.record_type = f"{self.record_type} - {self.record_owner} - {date.today()}"

    def __repr__(self):
        return f"{self.record_type} - {self.record_owner} - {self.amount}"

    def __str__(self):
        return self.__repr__()

class ModelResponse(BaseModel):
    status: str
    error: str = None
    message: str = None

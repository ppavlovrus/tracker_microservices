from dto import Record
from data_model import ModelRecord
from repository import BaseRepository

class TestService:
    def __init__(self, repository: BaseRepository):
     self.repository = repository

    async def create_record(self, record: Record) -> Record:
        new_record = ModelRecord(record_type=record.record_type, record_owner=record.record_owner, amount=record.amount)
        new_record.remove_fee_from_amount()
        new_record.add_date_to_record()
        saved_model = await self.repository.create(new_record)
        return Record(
            record_type=saved_model.record_type,
            record_owner=saved_model.record_owner,
            amount=saved_model.amount
        )

    async def get_record_by_id(self, record_id: int) -> Record | None:
        model = await self.repository.get_by_id(record_id)
        if model is None:
            return None
        return Record(
            record_type=model.record_type,
            record_owner=model.record_owner,
            amount=model.amount
        )

    async def get_all_records(self) -> list[Record]:
        models = await self.repository.get_all()
        return [
            Record(
                record_type=m.record_type,
                record_owner=m.record_owner,
                amount=m.amount
            )
            for m in models
        ]

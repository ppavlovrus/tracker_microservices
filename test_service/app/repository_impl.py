from repository import BaseRepository
from data_model import ModelRecord

class ModelRepository(BaseRepository):
    def __init__(self, pool):
      super().__init__(pool)

    async  def create(self, model_record: ModelRecord) -> ModelRecord:
        async with self.pool.acquire() as conn:
            try:
                new_id = await conn.fetchval("INSERT INTO main_records (record_type,record_owner,amount) VALUES ($1, $2, $3) RETURNING id",
                                   model_record.record_type, model_record.record_owner, model_record.amount)
                return ModelRecord(id=new_id, record_type=model_record.record_type, record_owner=model_record.record_owner, amount=model_record.amount)
            except Exception as e:
                print(f"Error is: {e}")
                raise

    async def update(self, model_record: ModelRecord) -> ModelRecord:
        if model_record.id is None:
            raise Exception("Record id is required for update operation")
        try:
            async with self.pool.acquire() as conn:
              updated_record = await conn.fetchrow("UPDATE main_records SET amount = $1, record_type = $2, record_owner = $3 where id = $4 RETURNING *",
                               model_record.amount, model_record.record_type, model_record.record_owner, model_record.id)
              if updated_record is None:
                raise Exception("Record not found")
              return ModelRecord(**dict(updated_record))
        except Exception as e:
            print(f"Error is: {e}")
            raise

    async def delete(self, record_id: int) -> bool:
        try:
            async with self.pool.acquire() as conn:
              result = await conn.execute("DELETE FROM main_records WHERE id = $1", record_id)
              rows_deleted = int(result.split()[1])
            return rows_deleted > 0
        except Exception as e:
            print("Error is: %s", e)
            raise

    async def get_all(self) -> list[ModelRecord]:
        try:
            async  with self.pool.acquire() as conn:
                all_records = await conn.fetch("SELECT * FROM main_records")
                return [ModelRecord(**dict(r)) for r in all_records]
        except Exception as e:
            print(f"Error is: {e}")
            raise

    async def get_by_id(self, record_id: int) -> ModelRecord | None:
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow("SELECT * FROM main_records WHERE id = $1", record_id)
                return ModelRecord(**dict(record)) if record else None
        except Exception as e:
            print(f"Error is: {e}")
            raise

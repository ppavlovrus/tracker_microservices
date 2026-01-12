from abc import ABC, abstractmethod
from data_model import ModelRecord

class BaseRepository(ABC):
    def __init__(self, pool):
        self.pool = pool

    @abstractmethod
    async  def create(self, ModRecord: ModelRecord):
        pass

    @abstractmethod
    async def update(self, ModRecord: ModelRecord, id: int):
        pass

    @abstractmethod
    async def delete(self, id: int):
        pass

    @abstractmethod
    async def get_by_id(self, record_id: int) -> ModelRecord | None:
        pass

    @abstractmethod
    async def get_all(self) -> list[ModelRecord]:
        pass


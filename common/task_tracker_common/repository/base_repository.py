from abc import ABC, abstractmethod
from typing import Optional, List

class DomainRepository(ABC):
    @abstractmethod
    async def get_by_id(self, id: int) -> Optional[object]:
        pass

    @abstractmethod
    async def create(self, obj: object) -> object:
        pass

    @abstractmethod
    async def update(self, obj: object) -> object:
        pass

    @abstractmethod
    async def delete(self, id: int) -> None:
        pass

    @abstractmethod
    async def get_all(self) -> List[object]:
        pass


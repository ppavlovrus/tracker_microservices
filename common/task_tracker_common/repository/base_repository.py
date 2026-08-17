from abc import ABC, abstractmethod


class DomainRepository(ABC):
    @abstractmethod
    async def get_by_id(self, id: int) -> object | None:
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
    async def get_all(self) -> list[object]:
        pass

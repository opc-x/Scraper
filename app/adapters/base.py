from abc import ABC, abstractmethod

from app.core.models import Job, SearchRequest


class BaseAdapter(ABC):
    name: str = ""

    @abstractmethod
    async def search(self, req: SearchRequest) -> list[Job]:
        ...

    @abstractmethod
    async def close(self):
        ...

from typing import Protocol


class AbstractTask(Protocol):
    @property
    def id(self) -> str: ...
    async def run(self) -> None: ...
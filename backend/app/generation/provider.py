from typing import Protocol

from app.generation.models import GenerationMessage, GenerationResult


class GenerationProvider(Protocol):
    async def generate(self, messages: list[GenerationMessage]) -> GenerationResult: ...

    async def aclose(self) -> None: ...

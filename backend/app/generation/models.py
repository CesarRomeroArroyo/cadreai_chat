from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class GenerationMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class GenerationResult:
    content: str
    usage: TokenUsage | None = None

"""Provider-neutral interfaces for models and search services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from src.models.evidence import SearchResult


Role = Literal["system", "user", "assistant"]


class ProviderError(RuntimeError):
    """A safe external-provider error that never includes credentials."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ModelResponse:
    content: str
    reasoning: str | None = None
    model: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    @abstractmethod
    def list_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def complete(
        self,
        messages: list[ChatMessage],
        *,
        enable_thinking: bool = False,
        reasoning_effort: str = "high",
    ) -> ModelResponse:
        raise NotImplementedError


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str) -> SearchResult:
        raise NotImplementedError


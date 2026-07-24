"""HKGAI Agenthub Search Agent implementation."""

from __future__ import annotations

from typing import Any

import requests

from src.config import Settings
from src.models.evidence import SearchResult
from src.providers.base import ProviderError, SearchProvider


class HKGAISearchProvider(SearchProvider):
    def __init__(
        self,
        settings: Settings,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "App-Name": self.settings.app_name,
            "App-Key": self.settings.app_key,
        }

    def search(self, query: str) -> SearchResult:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("search query cannot be empty")
        try:
            response = self.session.post(
                self.settings.agenthub_endpoint,
                headers=self._headers,
                json={"query": cleaned_query},
                timeout=self.settings.search_timeout_seconds,
            )
            response.raise_for_status()
            payload: Any = response.json()
        except requests.Timeout as exc:
            raise ProviderError("Agenthub request timed out") from exc
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            detail = f" (HTTP {status})" if status else ""
            raise ProviderError(f"Agenthub request failed{detail}") from exc
        except ValueError as exc:
            raise ProviderError("Agenthub returned non-JSON data") from exc

        if not isinstance(payload, dict):
            raise ProviderError("Agenthub returned an invalid JSON object")
        try:
            return SearchResult.from_agenthub(cleaned_query, payload)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc


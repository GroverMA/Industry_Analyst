"""Structured HKGAI REST search and crawler transport.

This transport exposes the same typed evidence contract as the MCP provider and
is used when MCP is unavailable. It does not invoke the expensive synchronous
Search Agent endpoint.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from src.config import Settings
from src.models.evidence import CrawlResult, WebSearchResult
from src.providers.base import ProviderError


RETRYABLE_STATUS_CODES = {502, 503, 504}


class HKGAIStructuredRestProvider:
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

    def search_web(self, query: str) -> WebSearchResult:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("search query cannot be empty")
        payload = self._post_json(
            f"{self.settings.search_base_url}/search",
            {
                "mode": "transparent",
                "engine": "tavily",
                "search_param": {"query": cleaned_query},
            },
        )
        try:
            return WebSearchResult.from_rest_payload(payload)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc

    def crawl_page(self, url: str) -> CrawlResult:
        cleaned_url = url.strip()
        if not cleaned_url:
            raise ValueError("crawl URL cannot be empty")
        payload = self._post_json(
            f"{self.settings.search_base_url}/crawler",
            {
                "mode": "transparent",
                "engine": "tavily",
                "crawler_param": {"urls": [cleaned_url]},
            },
        )
        try:
            return CrawlResult.from_rest_payload(payload)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc

    def _post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = self.session.post(
                    url,
                    headers=self._headers,
                    json=body,
                    timeout=self.settings.search_timeout_seconds,
                )
                if response.status_code in RETRYABLE_STATUS_CODES and attempt == 0:
                    time.sleep(0.25)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ProviderError("Structured REST returned invalid JSON")
                return payload
            except requests.Timeout as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.25)
                    continue
            except requests.RequestException as exc:
                status = getattr(exc.response, "status_code", None)
                detail = f" (HTTP {status})" if status else ""
                raise ProviderError(f"Structured REST request failed{detail}") from exc
            except ValueError as exc:
                raise ProviderError("Structured REST returned non-JSON data") from exc
        raise ProviderError("Structured REST request timed out after one retry") from last_error


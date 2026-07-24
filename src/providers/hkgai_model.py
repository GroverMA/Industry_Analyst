"""HKGAI Modelhub implementation using its OpenAI-compatible REST API."""

from __future__ import annotations

import json
from typing import Any

import requests

from src.config import Settings
from src.providers.base import ChatMessage, ModelProvider, ModelResponse, ProviderError


class HKGAIModelProvider(ModelProvider):
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
            "Authorization": f"Bearer {self.settings.model_api_key}",
            "Content-Type": "application/json",
        }

    def list_models(self) -> list[str]:
        payload = self._request_json(
            "GET", f"{self.settings.model_base_url}/v1/models"
        )
        records = payload.get("data", [])
        if not isinstance(records, list):
            raise ProviderError("Modelhub returned an invalid model list")
        return [
            str(record["id"])
            for record in records
            if isinstance(record, dict) and record.get("id")
        ]

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        enable_thinking: bool = False,
        reasoning_effort: str = "high",
    ) -> ModelResponse:
        body: dict[str, Any] = {
            "model": self.settings.model_name,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "stream": False,
        }
        if enable_thinking:
            body.update(
                {
                    "reasoning_effort": reasoning_effort,
                    "include_reasoning": True,
                    "chat_template_kwargs": {"enable_thinking": True},
                }
            )

        payload = self._request_json(
            "POST",
            f"{self.settings.model_base_url}/v1/chat/completions",
            json_body=body,
        )
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            content = message.get("content", "")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Modelhub returned an invalid completion") from exc

        usage = payload.get("usage", {})
        return ModelResponse(
            content=str(content or ""),
            reasoning=(
                str(message["reasoning"])
                if message.get("reasoning") is not None
                else None
            ),
            model=str(payload.get("model") or self.settings.model_name),
            usage=usage if isinstance(usage, dict) else {},
        )

    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        enable_thinking: bool = False,
    ) -> tuple[dict[str, Any], ModelResponse]:
        response = self.complete(messages, enable_thinking=enable_thinking)
        text = response.content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("Modelhub did not return valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ProviderError("Modelhub JSON response must be an object")
        return parsed, response

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                url,
                headers=self._headers,
                json=json_body,
                timeout=self.settings.model_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise ProviderError("Modelhub request timed out") from exc
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            detail = f" (HTTP {status})" if status else ""
            raise ProviderError(f"Modelhub request failed{detail}") from exc
        except ValueError as exc:
            raise ProviderError("Modelhub returned non-JSON data") from exc
        if not isinstance(payload, dict):
            raise ProviderError("Modelhub returned an invalid JSON object")
        return payload


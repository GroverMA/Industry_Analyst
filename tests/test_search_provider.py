from __future__ import annotations

from src.config import Settings
from src.providers.hkgai_search import HKGAISearchProvider


class FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "data": {
                "reasoning": "Found official sources.",
                "used_urls": [
                    "https://www.gov.cn/policy-a",
                    "https://www.gov.cn/policy-a",
                    "not-a-url",
                    "https://www.nmpa.gov.cn/policy-b",
                ],
                "extra_field": "preserved as field name",
            }
        }


class FakeSession:
    def __init__(self) -> None:
        self.last_request: dict | None = None

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.last_request = {"url": url, **kwargs}
        return FakeResponse()


def settings() -> Settings:
    return Settings(
        model_api_key="test-secret",
        model_base_url="https://model.example",
        model_name="test-model",
        agenthub_endpoint="https://search.example/v1/tool/search-agent",
        search_mcp_url="https://mcp.example/mcp",
        app_name="test-app",
        app_key="test-key",
    )


def test_search_returns_deduplicated_candidates() -> None:
    session = FakeSession()
    provider = HKGAISearchProvider(settings(), session=session)

    result = provider.search("official molecular diagnostics policy")

    assert len(result.candidates) == 2
    assert result.candidates[0].domain == "www.gov.cn"
    assert result.candidates[0].verified is False
    assert result.raw_data_fields == ["extra_field", "reasoning", "used_urls"]


def test_search_sends_runtime_credentials_without_logging_them() -> None:
    session = FakeSession()
    provider = HKGAISearchProvider(settings(), session=session)

    provider.search("test query")

    assert session.last_request is not None
    assert session.last_request["headers"]["App-Name"] == "test-app"
    assert session.last_request["headers"]["App-Key"] == "test-key"
    assert session.last_request["json"] == {"query": "test query"}

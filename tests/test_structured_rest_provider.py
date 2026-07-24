from __future__ import annotations

from src.config import Settings
from src.providers.hkgai_structured_rest import HKGAIStructuredRestProvider


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if url.endswith("/search"):
            return FakeResponse(
                {
                    "status": "success",
                    "engine": "tavily",
                    "search_results": {
                        "query": kwargs["json"]["search_param"]["query"],
                        "response_time": 0.2,
                        "results": [
                            {
                                "title": "Official source",
                                "url": "https://www.gov.cn/policy",
                                "content": "Summary",
                                "score": 0.9,
                            }
                        ],
                    },
                }
            )
        return FakeResponse(
            {
                "status": "success",
                "engine": "tavily",
                "crawler_results": {
                    "request_id": "request-1",
                    "response_time": 0.3,
                    "results": [
                        {
                            "url": kwargs["json"]["crawler_param"]["urls"][0],
                            "raw_content": "Page text",
                        }
                    ],
                    "failed_results": [],
                },
            }
        )


def settings() -> Settings:
    return Settings(
        model_api_key="test-secret",
        model_base_url="https://model.example",
        model_name="test-model",
        agenthub_endpoint="https://search.example/v1/tool/search-agent",
        search_mcp_url="https://mcp.example/mcp",
        app_name="test-app",
        app_key="test-key",
        search_base_url="https://search.example/v1",
    )


def test_structured_search_uses_transparent_tavily_mode() -> None:
    session = FakeSession()
    provider = HKGAIStructuredRestProvider(settings(), session=session)

    result = provider.search_web("industry policy")

    assert result.results[0].title == "Official source"
    assert session.calls[0]["json"] == {
        "mode": "transparent",
        "engine": "tavily",
        "search_param": {"query": "industry policy"},
    }
    assert session.calls[0]["headers"]["App-Key"] == "test-key"


def test_structured_crawler_uses_urls_array() -> None:
    session = FakeSession()
    provider = HKGAIStructuredRestProvider(settings(), session=session)

    result = provider.crawl_page("https://www.gov.cn/policy")

    assert result.pages[0].raw_content == "Page text"
    assert session.calls[0]["json"]["crawler_param"] == {
        "urls": ["https://www.gov.cn/policy"]
    }


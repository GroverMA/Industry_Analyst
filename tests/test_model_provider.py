from __future__ import annotations

import json

from src.config import Settings
from src.providers.base import ChatMessage
from src.providers.hkgai_model import HKGAIModelProvider


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.last_request: dict | None = None

    def request(self, method: str, url: str, **kwargs) -> FakeResponse:
        self.last_request = {"method": method, "url": url, **kwargs}
        if method == "GET":
            return FakeResponse({"data": [{"id": "test-model"}]})
        return FakeResponse(
            {
                "model": "test-model",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "industry": "工业机器人",
                                    "region": "全球",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 20},
            }
        )


def settings() -> Settings:
    return Settings(
        model_api_key="test-secret",
        model_base_url="https://model.example",
        model_name="test-model",
        agenthub_endpoint="https://search.example",
        search_mcp_url="https://mcp.example/mcp",
        app_name="test-app",
        app_key="test-key",
    )


def test_list_models_uses_bearer_auth() -> None:
    session = FakeSession()
    provider = HKGAIModelProvider(settings(), session=session)

    assert provider.list_models() == ["test-model"]
    assert session.last_request is not None
    assert session.last_request["url"] == "https://model.example/v1/models"
    assert session.last_request["headers"]["Authorization"] == "Bearer test-secret"


def test_complete_json_parses_model_content() -> None:
    session = FakeSession()
    provider = HKGAIModelProvider(settings(), session=session)

    parsed, response = provider.complete_json(
        [ChatMessage(role="user", content="Return JSON")]
    )

    assert parsed["industry"] == "工业机器人"
    assert parsed["region"] == "全球"
    assert response.usage["total_tokens"] == 20


def test_complete_json_extracts_object_from_markdown_and_explanation() -> None:
    session = FakeSession()
    provider = HKGAIModelProvider(settings(), session=session)
    response_text = "以下是结果：\n```json\n{\"industry\": \"工业机器人\"}\n```\n请审阅。"

    assert provider._extract_json_object(response_text) == {
        "industry": "工业机器人"
    }


def test_complete_json_handles_braces_inside_json_strings() -> None:
    session = FakeSession()
    provider = HKGAIModelProvider(settings(), session=session)
    response_text = '说明文字 {\"note\": \"比较集合{A与B}\", \"valid\": true} 结束'

    assert provider._extract_json_object(response_text) == {
        "note": "比较集合{A与B}",
        "valid": True,
    }


def test_complete_json_falls_back_to_reasoning_field() -> None:
    session = FakeSession()
    provider = HKGAIModelProvider(settings(), session=session)
    provider.complete = lambda *args, **kwargs: __import__(
        "src.providers.base", fromlist=["ModelResponse"]
    ).ModelResponse(
        content="",
        reasoning='推理完成。最终对象：{\"industry\": \"工业机器人\"}',
        model="test-model",
        usage={},
    )

    parsed, _ = provider.complete_json(
        [ChatMessage(role="user", content="Return JSON")],
        enable_thinking=True,
    )

    assert parsed == {"industry": "工业机器人"}


def test_thinking_parameters_are_only_added_when_enabled() -> None:
    session = FakeSession()
    provider = HKGAIModelProvider(settings(), session=session)

    provider.complete(
        [ChatMessage(role="user", content="Think")],
        enable_thinking=True,
        reasoning_effort="max",
    )

    assert session.last_request is not None
    body = session.last_request["json"]
    assert body["reasoning_effort"] == "max"
    assert body["include_reasoning"] is True
    assert body["chat_template_kwargs"] == {"enable_thinking": True}

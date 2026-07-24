"""Runtime configuration for local development and Streamlit deployment.

Public endpoint defaults live in code. Credentials are injected at runtime from
Streamlit Secrets or environment variables and are never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv


DEFAULT_MODEL_BASE_URL = "https://test-new-api.hkchat.app"
DEFAULT_MODEL_NAME = "t2_hkgai-v3_fp8_1m_e7"
DEFAULT_AGENTHUB_ENDPOINT = (
    "https://search-agent.prod.hkchat.app/v1/tool/search-agent"
)
DEFAULT_SEARCH_MCP_URL = "https://search-agent-mcp.prod.hkchat.app/mcp"
DEFAULT_SEARCH_BASE_URL = "https://search-agent.prod.hkchat.app/v1"
VALID_SEARCH_TRANSPORTS = {"auto", "mcp", "rest"}


class ConfigurationError(RuntimeError):
    """Raised when a required runtime setting is absent or invalid."""


def _streamlit_secret(name: str) -> str | None:
    """Read a Streamlit secret when running in Streamlit.

    Streamlit is deliberately an optional dependency in Stage 1, so command-line
    validation remains lightweight.
    """

    try:
        import streamlit as st  # type: ignore[import-not-found]

        value: Any = st.secrets.get(name)
    except (ImportError, FileNotFoundError, KeyError, RuntimeError):
        return None
    return str(value).strip() if value is not None else None


def _get_setting(name: str, default: str | None = None) -> str | None:
    value = _streamlit_secret(name) or os.getenv(name) or default
    return value.strip() if value else None


def _positive_int(name: str, default: int) -> int:
    raw = _get_setting(name, str(default))
    try:
        value = int(raw or default)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    model_api_key: str
    model_base_url: str
    model_name: str
    agenthub_endpoint: str
    search_mcp_url: str
    app_name: str
    app_key: str
    search_base_url: str = DEFAULT_SEARCH_BASE_URL
    search_transport: str = "auto"
    model_timeout_seconds: int = 120
    search_timeout_seconds: int = 300

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        values = {
            "model_api_key": _get_setting("HKGAI_MODEL_API_KEY"),
            "model_base_url": _get_setting(
                "HKGAI_MODEL_BASE_URL", DEFAULT_MODEL_BASE_URL
            ),
            "model_name": _get_setting("HKGAI_MODEL_NAME", DEFAULT_MODEL_NAME),
            "agenthub_endpoint": _get_setting(
                "HKGAI_AGENTHUB_ENDPOINT", DEFAULT_AGENTHUB_ENDPOINT
            ),
            "search_mcp_url": _get_setting(
                "HKGAI_SEARCH_MCP_URL", DEFAULT_SEARCH_MCP_URL
            ),
            "app_name": _get_setting("HKGAI_APP_NAME"),
            "app_key": _get_setting("HKGAI_APP_KEY"),
            "search_base_url": _get_setting(
                "HKGAI_SEARCH_BASE_URL", DEFAULT_SEARCH_BASE_URL
            ),
            "search_transport": _get_setting("HKGAI_SEARCH_TRANSPORT", "auto"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            env_names = {
                "model_api_key": "HKGAI_MODEL_API_KEY",
                "model_base_url": "HKGAI_MODEL_BASE_URL",
                "model_name": "HKGAI_MODEL_NAME",
                "agenthub_endpoint": "HKGAI_AGENTHUB_ENDPOINT",
                "search_mcp_url": "HKGAI_SEARCH_MCP_URL",
                "app_name": "HKGAI_APP_NAME",
                "app_key": "HKGAI_APP_KEY",
                "search_base_url": "HKGAI_SEARCH_BASE_URL",
                "search_transport": "HKGAI_SEARCH_TRANSPORT",
            }
            readable = ", ".join(env_names[name] for name in missing)
            raise ConfigurationError(f"Missing required configuration: {readable}")

        search_transport = str(values["search_transport"]).lower()
        if search_transport not in VALID_SEARCH_TRANSPORTS:
            allowed = ", ".join(sorted(VALID_SEARCH_TRANSPORTS))
            raise ConfigurationError(
                f"HKGAI_SEARCH_TRANSPORT must be one of: {allowed}"
            )

        return cls(
            model_api_key=str(values["model_api_key"]),
            model_base_url=str(values["model_base_url"]).rstrip("/"),
            model_name=str(values["model_name"]),
            agenthub_endpoint=str(values["agenthub_endpoint"]),
            search_mcp_url=str(values["search_mcp_url"]),
            app_name=str(values["app_name"]),
            app_key=str(values["app_key"]),
            search_base_url=str(values["search_base_url"]).rstrip("/"),
            search_transport=search_transport,
            model_timeout_seconds=_positive_int(
                "HKGAI_MODEL_TIMEOUT_SECONDS", 120
            ),
            search_timeout_seconds=_positive_int(
                "HKGAI_SEARCH_TIMEOUT_SECONDS", 300
            ),
        )

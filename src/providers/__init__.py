"""External capability providers."""

from .base import ChatMessage, ModelResponse, ProviderError
from .hkgai_model import HKGAIModelProvider
from .hkgai_mcp import HKGAIMCPProvider, MCPToolDefinition
from .hkgai_search import HKGAISearchProvider
from .hkgai_structured_rest import HKGAIStructuredRestProvider
from .search_router import RoutedCrawlResult, RoutedSearchResult, SearchRouter

__all__ = [
    "ChatMessage",
    "HKGAIModelProvider",
    "HKGAIMCPProvider",
    "HKGAISearchProvider",
    "HKGAIStructuredRestProvider",
    "MCPToolDefinition",
    "ModelResponse",
    "ProviderError",
    "RoutedCrawlResult",
    "RoutedSearchResult",
    "SearchRouter",
]

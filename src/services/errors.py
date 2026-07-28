"""Stable service exceptions shared across Streamlit hot reloads."""


class FutureIntelligenceError(ValueError):
    """Raised when a forecast violates evidence or scenario boundaries."""

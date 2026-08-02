"""Session-scoped research path used to switch between build-first and review-first UX."""

from __future__ import annotations

from collections.abc import MutableMapping
from enum import StrEnum
from typing import Any


USER_ROLE_KEY = "industry_analyst_user_role"


class UserRole(StrEnum):
    CONSULTANT = "consultant"
    REVIEWER = "reviewer"


ROLE_LABELS = {
    UserRole.CONSULTANT: "构建式研究",
    UserRole.REVIEWER: "审阅式研究",
}

ROLE_NOTES = {
    UserRole.CONSULTANT: "Research Build First · 从问题开始",
    UserRole.REVIEWER: "Report Review First · 从完整初稿开始",
}


def get_user_role(state: MutableMapping[str, Any]) -> UserRole | None:
    value = state.get(USER_ROLE_KEY)
    if value is None:
        return None
    try:
        return UserRole(value)
    except ValueError:
        state.pop(USER_ROLE_KEY, None)
        return None


def set_user_role(state: MutableMapping[str, Any], role: UserRole) -> None:
    state[USER_ROLE_KEY] = role.value

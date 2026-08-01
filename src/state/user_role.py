"""Session-scoped product role used to switch between authoring and review UX."""

from __future__ import annotations

from collections.abc import MutableMapping
from enum import StrEnum
from typing import Any


USER_ROLE_KEY = "industry_analyst_user_role"


class UserRole(StrEnum):
    CONSULTANT = "consultant"
    REVIEWER = "reviewer"


ROLE_LABELS = {
    UserRole.CONSULTANT: "Consultant · 咨询分析人员",
    UserRole.REVIEWER: "Reviewer · 审阅人员",
}

ROLE_NOTES = {
    UserRole.CONSULTANT: "撰写报告的人",
    UserRole.REVIEWER: "审阅报告的人",
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

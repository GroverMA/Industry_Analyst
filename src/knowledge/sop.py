"""Load and fingerprint the active research-methodology pack."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


DEFAULT_SOP_PATH = (
    Path(__file__).resolve().parents[2]
    / "knowledge_packs"
    / "research_sop"
    / "sullivan_industry_research_v1.json"
)


class SOPRule(BaseModel):
    rule_id: str
    title: str
    instruction: str
    applies_to: list[str] = Field(min_length=1)


class SOPConstraints(BaseModel):
    min_key_questions: int = 5
    max_key_questions: int = 12
    min_hypotheses: int = 3
    min_tasks: int = 5
    max_tasks: int = 10
    min_human_review_gates: int = 2
    require_inclusions_and_exclusions: bool = True
    require_counter_evidence: bool = True
    required_research_modules: list[str] = Field(default_factory=list)
    driver_factor_target: int = 4
    constraint_factor_target: int = 4
    source_tier_count: int = 4


class ResearchSOPPack(BaseModel):
    sop_id: str
    display_name: str
    version: str
    pack_type: str
    locked: bool = True
    description: str
    rules: list[SOPRule] = Field(min_length=1)
    constraints: SOPConstraints = Field(default_factory=SOPConstraints)
    content_hash: str = ""

    @property
    def rule_ids(self) -> list[str]:
        return [rule.rule_id for rule in self.rules]

    def prompt_context(self, artifact: str) -> str:
        relevant = [
            rule
            for rule in self.rules
            if artifact in rule.applies_to or "all" in rule.applies_to
        ]
        rules = "\n".join(
            f"- [{rule.rule_id}] {rule.title}: {rule.instruction}"
            for rule in relevant
        )
        return (
            f"SOP ID: {self.sop_id}\n"
            f"SOP name: {self.display_name}\n"
            f"Version: {self.version}\n"
            f"Locked: {self.locked}\n"
            f"Rules:\n{rules}\n"
            f"Constraints: {self.constraints.model_dump_json()}"
        )


def load_sop_pack(path: Path) -> ResearchSOPPack:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    payload["content_hash"] = hashlib.sha256(raw).hexdigest()
    return ResearchSOPPack.model_validate(payload)


def load_active_sop() -> ResearchSOPPack:
    configured = os.getenv("RESEARCH_SOP_PACK_PATH")
    path = Path(configured).expanduser() if configured else DEFAULT_SOP_PATH
    return load_sop_pack(path)

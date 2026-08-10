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
    / "trident_industry_research_v2.json"
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


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
    historical_observation_years: int = 10
    future_outlook_years: int = 5
    driver_core_min: int = 6
    driver_core_max: int = 10
    driver_body_min: int = 3
    driver_body_max: int = 5
    report_section_order: list[str] = Field(
        default_factory=lambda: [
            "industry_definition",
            "industry_track_value_chain",
            "market_sizing",
            "competitive_landscape",
            "drivers_future_outlook",
        ]
    )


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
    if not configured:
        return load_sop_pack(DEFAULT_SOP_PATH)

    configured_path = Path(configured).expanduser()
    candidates = [configured_path]
    if not configured_path.is_absolute():
        candidates.append(REPOSITORY_ROOT / configured_path)

    for candidate in candidates:
        if candidate.is_file():
            return load_sop_pack(candidate)

    # Streamlit secrets may retain a path from an earlier SOP filename after
    # a knowledge-pack migration.  A stale optional override must never make
    # the entire research workflow unavailable when the bundled, versioned
    # production pack is present.
    return load_sop_pack(DEFAULT_SOP_PATH)

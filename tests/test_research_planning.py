from __future__ import annotations

from typing import Any

import pytest

from src.knowledge.sop import load_active_sop
from src.providers.base import ChatMessage, ModelResponse
from src.services.research_planning import ResearchPlanningService, SOPComplianceError
from src.state.project import ProjectState


def project() -> ProjectState:
    return ProjectState(
        project_name="Global Robotics Study",
        industry="Industrial Robotics",
        region="Global",
        target_company="Example Robotics",
        decision_context="Choose the next three-year market entry priorities",
        research_objective="Assess competitors, drivers, and future trends",
        time_horizon="2026-2029",
    )


def brief_payload() -> dict[str, Any]:
    return {
        "decision_statement": "Decide market entry priorities.",
        "interpreted_intent": {
            "interpreted_objective": "Assess entry priorities semantically.",
            "requested_topics": ["competitors", "development conditions", "future trends"],
            "must_answer_questions": [f"Question {index}" for index in range(1, 6)],
            "terminology_map": {"development conditions": "drivers, constraints, and enabling conditions"},
            "explicit_exclusions": [],
            "ambiguities": ["Confirm application scope"],
        },
        "market_definition": {
            "core_market": "Industrial robotics",
            "product_scope": "Industrial robot systems",
            "customer_scope": "Manufacturing enterprises",
            "geography_scope": "Global",
            "value_chain_scope": "Equipment and system integration",
            "time_scope": "2026-2029",
            "inclusions": ["Robot equipment"],
            "exclusions": ["Consumer robots"],
        },
        "key_questions": [f"Question {index}" for index in range(1, 6)],
        "information_gaps": ["Comparable market shares"],
        "hypotheses": ["H1", "H2", "H3"],
        "clarification_questions": ["Confirm application scope"],
        "confidence_note": "Definitions require user confirmation.",
    }


def plan_payload() -> dict[str, Any]:
    tasks = []
    for index in range(1, 7):
        tasks.append(
            {
                "task_id": f"T{index:02d}",
                "title": f"Task {index}",
                "objective": "Answer a defined research question",
                "questions": ["What must be established?"],
                "hypotheses": ["A testable hypothesis"],
                "information_needs": ["Primary data"],
                "preferred_sources": ["Regulator", "Company filing"],
                "search_queries": ["industrial robotics filing"],
                "deliverables": ["Evidence table"],
                "evidence_standard": "Two independent sources",
                "counter_evidence_required": True,
                "validation_gate": "Human verifies evidence coverage",
                "depends_on": [] if index == 1 else [f"T{index - 1:02d}"],
                "prompt_question_ids": [f"Q{min(index, 5)}"],
            }
        )
    return {
        "plan_summary": "Professional SOP-governed evidence-first plan.",
        "tasks": tasks,
        "human_review_gates": [
            "Confirm scope",
            "Approve evidence",
            "Approve report content",
        ],
        "unresolved_gaps": ["Market-share definition"],
        "sop_coverage": {
            "industry_definition": ["T01"],
            "industry_track": ["T01"],
            "value_chain": ["T02"],
            "market_sizing": ["T03"],
            "competitive_landscape": ["T04"],
            "drivers_constraints": ["T05"],
            "future_intelligence": ["T06"],
        },
        "prompt_question_coverage": {
            "Q1": ["T01"],
            "Q2": ["T02"],
            "Q3": ["T03"],
            "Q4": ["T04"],
            "Q5": ["T05", "T06"],
        },
    }


class FakeStructuredModel:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.messages: list[list[ChatMessage]] = []

    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        enable_thinking: bool = False,
    ) -> tuple[dict[str, Any], ModelResponse]:
        self.messages.append(messages)
        return self.responses.pop(0), ModelResponse(content="{}", model="fake")


def test_active_sop_is_locked_and_fingerprinted() -> None:
    sop = load_active_sop()

    assert sop.locked is True
    assert sop.content_hash
    assert sop.sop_id == "trident_industry_research"
    assert sop.version == "2.0.0"
    assert "SUL-DEFINE-001" in sop.rule_ids
    assert "SUL-SIZE-003" in sop.rule_ids


def test_service_generates_traceable_brief_and_plan() -> None:
    fake = FakeStructuredModel([brief_payload(), plan_payload()])
    service = ResearchPlanningService(fake, load_active_sop())

    brief = service.generate_brief(project())
    brief = brief.model_copy(update={"human_confirmed": True})
    plan = service.generate_plan(project(), brief)

    assert brief.methodology.locked is True
    assert brief.methodology.sop_hash
    assert len(brief.key_questions) == 5
    assert len(plan.tasks) == 6
    assert all(task.counter_evidence_required for task in plan.tasks)
    assert set(plan.sop_coverage) == set(load_active_sop().constraints.required_research_modules)
    assert plan.methodology.sop_id == brief.methodology.sop_id
    assert "当前研究方法包处于锁定状态" in fake.messages[0][0].content


def test_service_rejects_plan_without_counter_evidence() -> None:
    invalid = plan_payload()
    invalid["tasks"][0]["counter_evidence_required"] = False
    fake = FakeStructuredModel([brief_payload(), invalid, invalid])
    service = ResearchPlanningService(fake, load_active_sop())

    with pytest.raises(SOPComplianceError, match="反证"):
        brief = service.generate_brief(project()).model_copy(update={"human_confirmed": True})
        service.generate_plan(project(), brief)


def test_service_repairs_a_noncompliant_plan_once() -> None:
    invalid = plan_payload()
    invalid["tasks"][0]["search_queries"] = []
    fake = FakeStructuredModel([brief_payload(), invalid, plan_payload()])
    service = ResearchPlanningService(fake, load_active_sop())

    brief = service.generate_brief(project())
    brief = brief.model_copy(update={"human_confirmed": True})
    plan = service.generate_plan(project(), brief)

    assert len(plan.tasks) == 6
    assert len(fake.messages) == 3
    assert "违规原因" in fake.messages[-1][-1].content


def test_plan_requires_gate_zero_confirmation() -> None:
    fake = FakeStructuredModel([brief_payload()])
    service = ResearchPlanningService(fake, load_active_sop())
    brief = service.generate_brief(project())

    with pytest.raises(SOPComplianceError, match="Gate 0"):
        service.generate_plan(project(), brief)


def test_service_rejects_plan_without_full_sop_coverage() -> None:
    invalid = plan_payload()
    invalid["sop_coverage"].pop("market_sizing")
    fake = FakeStructuredModel([brief_payload(), invalid, invalid])
    service = ResearchPlanningService(fake, load_active_sop())

    with pytest.raises(SOPComplianceError, match="完整覆盖"):
        brief = service.generate_brief(project()).model_copy(update={"human_confirmed": True})
        service.generate_plan(project(), brief)


def test_service_rejects_formal_prompt_mapping_not_declared_by_task() -> None:
    invalid = plan_payload()
    invalid["tasks"][0]["prompt_question_ids"] = ["Q2"]
    fake = FakeStructuredModel([brief_payload(), invalid, invalid])
    service = ResearchPlanningService(fake, load_active_sop())

    with pytest.raises(SOPComplianceError, match="未声明其承担"):
        brief = service.generate_brief(project()).model_copy(update={"human_confirmed": True})
        service.generate_plan(project(), brief)

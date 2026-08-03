from __future__ import annotations

from pydantic import ValidationError

from src.models.analysis import IndustryAnalysisArtifact
from src.models.evidence import EvidenceCollectionArtifact
from src.models.future import FutureIntelligenceArtifact
from src.models.research import (
    MarketDefinition,
    MethodologyTrace,
    ResearchBriefArtifact,
    ResearchPlanArtifact,
)
from src.state.project import ProjectState, ResearchMode, WorkflowStatus, WorkspaceMode
from src.state.project import rewind_to_previous_review_gate
from src.state.browser_history import (
    build_project_record,
    project_is_complete,
    project_node_label,
    project_progress,
    resume_page_for_project,
)
from src.state.session import PROJECT_KEY, clear_project, get_project, set_project


def make_project() -> ProjectState:
    return ProjectState(
        project_name="Global Robotics Study",
        industry="Industrial Robotics",
        region="Global",
        target_company=None,
        decision_context="Choose a market entry strategy",
        research_objective="Assess competitors, drivers, and future trends",
        time_horizon="2026-2030",
    )


def test_general_project_is_industry_neutral() -> None:
    project = make_project()

    assert project.industry == "Industrial Robotics"
    assert project.research_mode == ResearchMode.GENERAL
    assert project.industry_pack is None
    assert project.workflow_status["research_brief"] == WorkflowStatus.READY
    assert project.completion_ratio == 0


def test_project_rejects_blank_required_fields() -> None:
    try:
        ProjectState(
            project_name=" ",
            industry="Software",
            region="Global",
            decision_context="Decide",
            research_objective="Research",
            time_horizon="2026",
        )
    except ValidationError:
        return
    raise AssertionError("blank project name should fail validation")


def test_project_allows_exploratory_research_without_business_decision() -> None:
    project = ProjectState(
        project_name="Industry Landscape",
        industry="Industrial Robotics",
        region="Global",
        research_objective="Understand the industry, competitors, and trends",
        time_horizon="2026-2030",
    )

    assert project.decision_context is None


def test_company_strategy_path_requires_target_company_and_strategy_objective() -> None:
    try:
        ProjectState(
            project_name="Company Strategy",
            industry="Diagnostics",
            region="China",
            company_strategy_enabled=True,
            research_objective="Assess the market",
            time_horizon="2026-2030",
        )
    except ValidationError:
        return
    raise AssertionError("company strategy path should require company and objective")


def test_company_strategy_path_accepts_explicit_strategic_intent() -> None:
    project = ProjectState(
        project_name="Company Strategy",
        industry="Diagnostics",
        region="China",
        target_company="Demo Diagnostics",
        company_strategy_enabled=True,
        company_strategy_objective="Protect the core business while entering digital PCR",
        research_objective="Assess the market",
        time_horizon="2026-2030",
    )

    assert project.company_strategy_enabled is True
    assert project.company_strategy_objective.startswith("Protect")


def test_not_applicable_steps_are_excluded_from_completion_ratio() -> None:
    project = make_project()
    statuses = dict(project.workflow_status)
    statuses["research_brief"] = WorkflowStatus.COMPLETED
    statuses["company_assessment"] = WorkflowStatus.NOT_APPLICABLE
    statuses["action_plan"] = WorkflowStatus.NOT_APPLICABLE

    updated = project.model_copy(update={"workflow_status": statuses})

    assert updated.completion_ratio == 1 / 8


def test_project_snapshot_preserves_workspace_mode() -> None:
    project = make_project().model_copy(
        update={"workspace_mode": WorkspaceMode.ANALYST_WORKSPACE}
    )

    restored = ProjectState.model_validate_json(project.model_dump_json())

    assert restored == project
    assert restored.workspace_mode == WorkspaceMode.ANALYST_WORKSPACE


def test_workflow_status_update_is_immutable() -> None:
    project = make_project()

    updated = project.update_step("research_brief", WorkflowStatus.COMPLETED)

    assert project.workflow_status["research_brief"] == WorkflowStatus.READY
    assert updated.workflow_status["research_brief"] == WorkflowStatus.COMPLETED


def test_session_helpers_round_trip_project() -> None:
    state: dict = {}
    project = make_project()

    set_project(state, project)
    assert isinstance(state[PROJECT_KEY], dict)
    assert get_project(state) == project
    clear_project(state)
    assert get_project(state) is None


def test_session_migrates_legacy_nested_brief_missing_new_field() -> None:
    brief = ResearchBriefArtifact(
        decision_statement="研究中国IVD行业",
        original_prompt="研究中国IVD行业",
        market_definition=MarketDefinition(
            core_market="中国IVD市场",
            product_scope="体外诊断产品",
            customer_scope="医疗机构",
            geography_scope="中国",
            value_chain_scope="上游至终端",
            time_scope="2020-2036",
            inclusions=["诊断试剂"],
            exclusions=["治疗药物"],
        ),
        key_questions=["市场规模如何？"],
        information_gaps=["统计口径待确认"],
        hypotheses=["需求持续增长"],
        clarification_questions=["历史期与预测期如何划分？"],
        confidence_note="待核验",
        methodology=MethodologyTrace(
            sop_id="SOP-TEST",
            sop_name="测试SOP",
            sop_version="1.0",
            sop_hash="test",
            rule_ids=["R1"],
        ),
    )
    # Simulate a nested model retained in Streamlit memory from the version
    # before clarification_responses was introduced.
    brief.__dict__.pop("clarification_responses")
    legacy_project = make_project().model_copy(
        update={"research_brief_artifact": brief}
    )
    state = {PROJECT_KEY: legacy_project}

    restored = get_project(state)

    assert restored is not None
    assert restored.research_brief_artifact is not None
    assert restored.research_brief_artifact.clarification_responses == {}
    assert isinstance(state[PROJECT_KEY], dict)


def test_browser_history_record_preserves_full_resumable_project() -> None:
    project = make_project().update_step("industry_analysis", WorkflowStatus.NEEDS_REVIEW)

    record = build_project_record(project, "research_studio")
    restored = ProjectState.model_validate(record["project_state"])

    assert restored == project
    assert record["project_id"] == project.project_id
    assert record["active_page"] == "research_studio"
    assert record["status_group"] == "in_progress"
    assert "待审核" in record["node_label"]


def test_project_history_progress_excludes_non_applicable_steps() -> None:
    project = make_project()
    statuses = dict(project.workflow_status)
    statuses["research_brief"] = WorkflowStatus.COMPLETED
    statuses["company_assessment"] = WorkflowStatus.NOT_APPLICABLE
    statuses["action_plan"] = WorkflowStatus.NOT_APPLICABLE
    project = project.model_copy(update={"workflow_status": statuses})

    assert project_progress(project) == 12
    assert project_is_complete(project) is False
    assert project_node_label(project) == "Research Brief"


def test_history_resume_uses_latest_work_page_instead_of_project_home() -> None:
    project = make_project().model_copy(update={"current_step": "evidence_qa"})

    assert resume_page_for_project(project, "home") == "research_studio"
    assert resume_page_for_project(project, "evidence_analysis") == "evidence_analysis"


def test_rewind_to_gate_zero_keeps_editable_brief_and_invalidates_later_work() -> None:
    brief = ResearchBriefArtifact.model_construct(human_confirmed=True)
    plan = ResearchPlanArtifact.model_construct()
    project = make_project().model_copy(
        update={"research_brief_artifact": brief, "research_plan_artifact": plan}
    )

    result = rewind_to_previous_review_gate(project)

    assert result is not None
    rewound, _ = result
    assert rewound.current_step == "research_brief"
    assert rewound.research_brief_artifact is not None
    assert rewound.research_brief_artifact.human_confirmed is False
    assert rewound.research_plan_artifact is None


def test_rewind_from_analysis_returns_to_gate_one_and_clears_stale_outputs() -> None:
    evidence = EvidenceCollectionArtifact.model_construct(human_confirmed=True)
    analysis = IndustryAnalysisArtifact.model_construct(human_confirmed=False)
    project = make_project().model_copy(
        update={
            "evidence_collection_artifact": evidence,
            "industry_analysis_artifact": analysis,
        }
    )

    result = rewind_to_previous_review_gate(project)

    assert result is not None
    rewound, _ = result
    assert rewound.current_step == "evidence_qa"
    assert rewound.evidence_collection_artifact.human_confirmed is False
    assert rewound.industry_analysis_artifact is None


def test_rewind_after_gate_two_returns_to_content_review() -> None:
    analysis = IndustryAnalysisArtifact.model_construct(human_confirmed=True)
    future = FutureIntelligenceArtifact.model_construct(human_confirmed=True)
    project = make_project().model_copy(
        update={
            "industry_analysis_artifact": analysis,
            "future_intelligence_artifact": future,
            "general_report_artifact": object(),
        }
    )

    result = rewind_to_previous_review_gate(project)

    assert result is not None
    rewound, _ = result
    assert rewound.current_step == "human_review"
    assert rewound.industry_analysis_artifact.human_confirmed is False
    assert rewound.future_intelligence_artifact.human_confirmed is False
    assert rewound.general_report_artifact is None

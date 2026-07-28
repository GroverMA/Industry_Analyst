from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.models.analysis import (
    AnalysisFinding,
    AnalysisFindingType,
    IndustryAnalysisArtifact,
    IndustryAnalysisModule,
)
from src.models.evidence import (
    EvidenceCollectionArtifact,
    EvidenceItem,
    EvidenceKind,
    EvidenceReviewStatus,
    EvidenceSource,
    SourceTier,
    TaskEvidenceRun,
)
from src.models.research import (
    MarketDefinition,
    MethodologyTrace,
    ResearchBriefArtifact,
    ResearchIntent,
    ResearchPlanArtifact,
    ResearchTask,
)
from src.state.project import ProjectState
from src.state.session import ACTIVE_PAGE_KEY, PROJECT_KEY
from src.ui.pages.research_studio import _recommended_evidence_ids


def test_gate_one_recommendations_cover_each_research_task() -> None:
    def task(task_id: str, prompt_id: str) -> ResearchTask:
        return ResearchTask(
            task_id=task_id,
            title=task_id,
            objective="test",
            questions=["必须回答的问题"],
            hypotheses=["hypothesis"],
            information_needs=["data"],
            preferred_sources=["official"],
            search_queries=["query"],
            deliverables=["evidence"],
            evidence_standard="traceable",
            validation_gate="human",
            prompt_question_ids=[prompt_id],
        )
    source_a = EvidenceSource(
        task_id="T01",
        discovery_query="query-a",
        title="Source A",
        url="https://example.com/a",
        domain="example.com",
        source_tier=SourceTier.B,
        tier_reason="industry source",
        transport="rest",
    )
    source_b = EvidenceSource(
        task_id="T02",
        discovery_query="query-b",
        title="Source B",
        url="https://example.com/b",
        domain="example.com",
        source_tier=SourceTier.C,
        tier_reason="secondary source",
        transport="rest",
    )
    high_qa = EvidenceItem(
        task_id="T01",
        source_id=source_a.source_id,
        kind=EvidenceKind.FACT,
        statement="高质量候选证据",
        supporting_excerpt="高质量候选证据",
        geographic_scope="中国",
        market_scope="测试行业",
        supports_or_challenges="supports",
        model_confidence=0.8,
        prompt_relevance=0.9,
        question_ids=["T01-Q1"],
        prompt_question_ids=["Q1"],
        qa_score=80,
    )
    low_qa = EvidenceItem(
        task_id="T02",
        source_id=source_b.source_id,
        kind=EvidenceKind.FACT,
        statement="唯一但需要重点核查的候选证据",
        supporting_excerpt="唯一但需要重点核查的候选证据",
        geographic_scope="中国",
        market_scope="测试行业",
        supports_or_challenges="supports",
        model_confidence=0.5,
        prompt_relevance=0.9,
        question_ids=["T02-Q1"],
        prompt_question_ids=["Q2"],
        qa_score=45,
    )
    artifact = EvidenceCollectionArtifact(
        research_plan_id="plan",
        task_runs=[
            TaskEvidenceRun(
                task_id="T01",
                task_title="Task A",
                queries_used=["query-a"],
                sources=[source_a],
                evidence=[high_qa],
            ),
            TaskEvidenceRun(
                task_id="T02",
                task_title="Task B",
                queries_used=["query-b"],
                sources=[source_b],
                evidence=[low_qa],
            ),
        ],
    )

    plan = type("Plan", (), {"tasks": [task("T01", "Q1"), task("T02", "Q2")]})()

    assert _recommended_evidence_ids(artifact, plan) == {high_qa.evidence_id}


def test_gate_one_recommendation_uses_minimum_question_cover() -> None:
    source = EvidenceSource(
        task_id="T01",
        discovery_query="query",
        title="Official source",
        url="https://example.gov.cn/source",
        domain="example.gov.cn",
        source_tier=SourceTier.A,
        tier_reason="official",
        transport="rest",
    )
    comprehensive = EvidenceItem(
        task_id="T01",
        source_id=source.source_id,
        kind=EvidenceKind.FACT,
        statement="一条证据直接回答两项问题。",
        supporting_excerpt="一条证据直接回答两项问题",
        geographic_scope="中国",
        market_scope="测试行业",
        supports_or_challenges="supports",
        model_confidence=0.9,
        prompt_relevance=0.95,
        question_ids=["T01-Q1", "T01-Q2"],
        prompt_question_ids=["Q1", "Q2"],
        qa_score=95,
    )
    partial = comprehensive.model_copy(
        update={
            "evidence_id": "EVD-partial",
            "statement": "仅回答第一项问题。",
            "question_ids": ["T01-Q1"],
            "prompt_question_ids": ["Q1"],
            "qa_score": 90,
        }
    )
    task = ResearchTask(
        task_id="T01",
        title="Task",
        objective="test",
        questions=["问题一", "问题二"],
        hypotheses=["hypothesis"],
        information_needs=["data"],
        preferred_sources=["official"],
        search_queries=["query one", "query two"],
        deliverables=["evidence"],
        evidence_standard="traceable",
        validation_gate="human",
        prompt_question_ids=["Q1", "Q2"],
    )
    artifact = EvidenceCollectionArtifact(
        research_plan_id="plan",
        task_runs=[
            TaskEvidenceRun(
                task_id="T01",
                task_title="Task",
                queries_used=["query"],
                sources=[source],
                evidence=[partial, comprehensive],
            )
        ],
    )
    plan = type("Plan", (), {"tasks": [task]})()

    assert _recommended_evidence_ids(artifact, plan) == {
        comprehensive.evidence_id
    }


def test_industry_analysis_workspace_renders_from_session_artifacts() -> None:
    trace = MethodologyTrace(
        sop_id="ui",
        sop_name="UI Test SOP",
        sop_version="1",
        sop_hash="abc",
        rule_ids=["ANALYSIS-001"],
    )
    source = EvidenceSource(
        task_id="T01",
        discovery_query="query",
        title="Official source",
        url="https://example.gov.cn/report",
        domain="example.gov.cn",
        source_tier=SourceTier.A,
        tier_reason="official",
        transport="rest",
        crawled=True,
    )
    evidence = EvidenceItem(
        task_id="T01",
        source_id=source.source_id,
        kind=EvidenceKind.FACT,
        statement="市场受到明确监管要求约束。",
        supporting_excerpt="市场受到明确监管要求约束",
        geographic_scope="中国",
        market_scope="测试行业",
        supports_or_challenges="supports",
        model_confidence=0.9,
        prompt_relevance=0.95,
        question_ids=["T01-Q1"],
        qa_score=95,
        review_status=EvidenceReviewStatus.ACCEPTED,
    )
    run = TaskEvidenceRun(
        task_id="T01",
        task_title="当前市场",
        queries_used=["query"],
        sources=[source],
        evidence=[evidence],
    )
    evidence_artifact = EvidenceCollectionArtifact(
        research_plan_id="plan",
        task_runs=[run],
        human_confirmed=True,
    )
    finding = AnalysisFinding(
        subject="测试行业",
        finding_type=AnalysisFindingType.ANALYST_INFERENCE,
        statement="监管要求构成当前市场进入约束。",
        mechanism="监管准入影响参与者进入市场的条件。",
        evidence_ids=[evidence.evidence_id],
        confidence=0.8,
        scope="中国测试行业",
        uncertainty="缺少细分产品数据",
        boundary_condition="不适用于非监管产品",
    )
    modules = [
        IndustryAnalysisModule(
            module_id=module_id,
            title=title,
            executive_summary="当前证据支持有限分析。",
            findings=[finding] if module_id == "market_value_chain" else [],
            evidence_gaps=[] if module_id == "market_value_chain" else ["需要更多证据"],
        )
        for module_id, title in (
            ("market_value_chain", "市场定义与价值链"),
            ("market_status", "市场现状与结构"),
            ("competitive_landscape", "竞争者与可比公司"),
            ("drivers_constraints", "驱动与制约因素"),
            ("commercial_logic", "当前商业逻辑"),
        )
    ]
    analysis = IndustryAnalysisArtifact(
        evidence_collection_id=evidence_artifact.artifact_id,
        input_evidence_ids=[evidence.evidence_id],
        modules=modules,
        methodology=trace,
    )
    task = ResearchTask(
        task_id="T01",
        title="当前市场",
        objective="研究当前市场",
        questions=["当前市场如何？"],
        hypotheses=["监管影响市场"],
        information_needs=["监管证据"],
        preferred_sources=["政府"],
        search_queries=["query"],
        deliverables=["分析"],
        evidence_standard="可追溯",
        validation_gate="人工审核",
    )
    plan = ResearchPlanArtifact(
        artifact_id="plan",
        plan_summary="plan",
        tasks=[task],
        human_review_gates=["gate"],
        methodology=trace,
        human_confirmed=True,
    )
    project = ProjectState(
        project_name="UI Analysis Test",
        industry="测试行业",
        region="中国",
        research_objective="测试行业分析页面",
        time_horizon="2024-2026",
        research_plan_artifact=plan,
        evidence_collection_artifact=evidence_artifact,
        industry_analysis_artifact=analysis,
    )

    app = AppTest.from_file("app.py")
    app.session_state[PROJECT_KEY] = project.model_dump(mode="json")
    app.session_state[ACTIVE_PAGE_KEY] = "evidence_analysis"
    app.run(timeout=10)

    assert not app.exception
    assert any("Industry Analysis" in item.value for item in app.subheader)
    assert any(button.label == "接受行业判断" for button in app.button)

    brief = ResearchBriefArtifact(
        decision_statement="测试行业分析页面",
        original_prompt="测试行业分析页面",
        interpreted_intent=ResearchIntent(
            interpreted_objective="测试行业分析页面",
            requested_topics=["市场情况"],
            must_answer_questions=["当前市场如何？"],
        ),
        market_definition=MarketDefinition(
            core_market="测试行业",
            product_scope="测试产品",
            customer_scope="测试客户",
            geography_scope="中国",
            value_chain_scope="全产业链",
            time_scope="2024-2026",
            inclusions=["核心产品"],
            exclusions=["相邻产品"],
        ),
        key_questions=["当前市场如何？"],
        information_gaps=["更多来源"],
        hypotheses=["监管影响市场"],
        confidence_note="待验证",
        methodology=trace,
        human_confirmed=True,
    )
    gap_plan = plan.model_copy(
        update={
            "tasks": [
                task.model_copy(
                    update={"questions": ["当前市场如何？", "市场为什么增长？"]}
                )
            ]
        }
    )
    studio_project = project.model_copy(
        update={
            "research_brief_artifact": brief,
            "research_plan_artifact": gap_plan,
            "evidence_collection_artifact": evidence_artifact.model_copy(
                update={"human_confirmed": False}
            ),
            "industry_analysis_artifact": None,
        }
    )
    studio = AppTest.from_file("app.py")
    studio.session_state[PROJECT_KEY] = studio_project.model_dump(mode="json")
    studio.session_state[ACTIVE_PAGE_KEY] = "research_studio"
    studio.run(timeout=10)

    assert not studio.exception
    labels = {button.label for button in studio.button}
    assert {"采用全部系统推荐", "一键全选", "全部取消"}.issubset(labels)
    assert "确认Gate 1并生成行业分析与趋势" in labels
    assert not any("补检" in label or "重新检索" in label for label in labels)
    assert "继续执行未完成检索" not in labels
    assert any("证据缺口不会阻断研究" in item.value for item in studio.warning)

    gate_zero_project = project.model_copy(
        update={
            "research_brief_artifact": brief.model_copy(
                update={"human_confirmed": False}
            ),
            "research_plan_artifact": None,
            "evidence_collection_artifact": None,
            "industry_analysis_artifact": None,
        }
    )
    gate_zero = AppTest.from_file("app.py")
    gate_zero.session_state[PROJECT_KEY] = gate_zero_project.model_dump(mode="json")
    gate_zero.session_state[ACTIVE_PAGE_KEY] = "research_studio"
    gate_zero.run(timeout=10)

    confirm_button = next(
        button for button in gate_zero.button
        if button.label == "确认Gate 0并开始网页研究"
    )
    assert confirm_button.disabled is False

    rewind_project = studio_project.model_copy(
        update={
            "evidence_collection_artifact": evidence_artifact,
            "industry_analysis_artifact": analysis,
            "current_step": "industry_analysis",
        }
    )
    rewind_app = AppTest.from_file("app.py")
    rewind_app.session_state[PROJECT_KEY] = rewind_project.model_dump(mode="json")
    rewind_app.session_state[ACTIVE_PAGE_KEY] = "research_studio"
    rewind_app.session_state["studio_gate_one_truth_confirmation"] = True
    rewind_app.session_state["studio_gate_two_confirmation"] = True
    rewind_app.run(timeout=10)

    rewind_button = next(
        button for button in rewind_app.button
        if button.label == "← 返回上一审核节点"
    )
    rewind_button.click().run(timeout=10)

    assert not rewind_app.exception
    rewound = ProjectState.model_validate(rewind_app.session_state[PROJECT_KEY])
    assert rewound.current_step == "evidence_qa"
    assert rewound.evidence_collection_artifact is not None
    assert rewound.evidence_collection_artifact.human_confirmed is False
    assert rewound.industry_analysis_artifact is None
    assert rewind_app.session_state["studio_gate_one_truth_confirmation"] is False
    assert "studio_gate_two_confirmation" not in rewind_app.session_state
    assert any("已返回Gate 1证据审核" in item.value for item in rewind_app.success)

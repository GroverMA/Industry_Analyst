from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src.knowledge.sop import load_active_sop
from src.models.analysis import (
    AnalysisFinding,
    AnalysisFindingType,
    AnalysisReviewStatus,
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
from src.models.future import ForecastReviewStatus
from src.models.research import (
    MarketDefinition,
    MethodologyTrace,
    ResearchBriefArtifact,
    ResearchIntent,
)
from src.providers.base import ModelResponse, ProviderError
from src.services.future_intelligence import (
    FutureIntelligenceError,
    FutureIntelligenceService,
    forecast_gate_reasons,
    review_forecast_item,
)
from src.services.industry_analysis import (
    EXPECTED_MODULES,
    IndustryAnalysisService,
    review_analysis_finding,
)
from src.services.report_export import (
    build_report_docx,
    build_report_pdf,
    project_report_context,
)
from src.services.report_generation import ReportGenerationService, generate_general_report
from src.state.project import ProjectState
from src.state.session import ACTIVE_PAGE_KEY, PROJECT_KEY


def fixtures():
    trace = MethodologyTrace(
        sop_id="test",
        sop_name="Test SOP",
        sop_version="1",
        sop_hash="abc",
        rule_ids=["TEST"],
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
        statement="监管准入要求正在提高。",
        supporting_excerpt="监管准入要求正在提高",
        geographic_scope="中国",
        market_scope="分子诊断",
        supports_or_challenges="supports",
        model_confidence=0.9,
        qa_score=90,
        review_status=EvidenceReviewStatus.ACCEPTED,
    )
    run = TaskEvidenceRun(
        task_id="T01",
        task_title="监管",
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
        subject="市场准入",
        finding_type=AnalysisFindingType.ANALYST_INFERENCE,
        statement="准入要求构成当前进入壁垒。",
        mechanism="监管要求增加合规资源需求。",
        evidence_ids=[evidence.evidence_id],
        confidence=0.8,
        scope="中国分子诊断",
        uncertainty="不同产品分类存在差异",
        boundary_condition="科研产品不适用",
        review_status=AnalysisReviewStatus.ACCEPTED,
    )
    modules = [
        IndustryAnalysisModule(
            module_id=module_id,
            title=module_id,
            executive_summary="summary",
            findings=[finding] if index == 0 else [],
            evidence_gaps=[] if index == 0 else ["gap"],
        )
        for index, module_id in enumerate(
            (
                "market_value_chain",
                "market_status",
                "competitive_landscape",
                "drivers_constraints",
                "commercial_logic",
            )
        )
    ]
    analysis = IndustryAnalysisArtifact(
        evidence_collection_id=evidence_artifact.artifact_id,
        input_evidence_ids=[evidence.evidence_id],
        modules=modules,
        methodology=trace,
        human_confirmed=True,
    )
    project = ProjectState(
        project_name="Future Test",
        industry="分子诊断",
        region="中国",
        research_objective="预测未来变化",
        time_horizon="2026-2030",
        research_brief_artifact=ResearchBriefArtifact(
            decision_statement="预测未来变化",
            original_prompt="预测未来变化",
            interpreted_intent=ResearchIntent(
                interpreted_objective="预测未来变化",
                requested_topics=["趋势"],
                must_answer_questions=["未来会发生什么变化？"],
            ),
            market_definition=MarketDefinition(
                core_market="分子诊断",
                product_scope="诊断产品与服务",
                customer_scope="医疗机构",
                geography_scope="中国",
                value_chain_scope="全产业链",
                time_scope="2026-2030",
                inclusions=["临床分子诊断"],
                exclusions=["纯科研产品"],
            ),
            key_questions=["未来会发生什么变化？"],
            information_gaps=["长期信号"],
            hypotheses=["监管要求继续提高"],
            confidence_note="待验证",
            methodology=trace,
            human_confirmed=True,
        ),
    )
    return project, evidence_artifact, analysis, evidence, finding


def payload(evidence_id: str, finding_id: str) -> dict:
    trend = {
        "trend_id": "TRD-01",
        "title": "合规能力重要性提高",
        "category": "policy_capital_value_chain",
        "forecast_horizon": "2026-2028",
        "forecast_year_end": 2028,
        "forecast_statement": "合规能力可能继续影响市场进入条件。",
        "observed_signals": [
            {
                "signal_type": "policy",
                "description": "监管准入要求正在提高",
                "actor": "监管机构",
                "signal_date": "2026",
                "evidence_ids": [evidence_id],
                "finding_ids": [finding_id],
                "direction": "supports",
            }
        ],
        "causal_mechanism": ["准入要求提高", "合规投入增加", "进入壁垒提高"],
        "assumptions": ["监管方向保持连续"],
        "affected_players": ["市场参与者"],
        "player_moves": [
            {
                "player": "市场参与者",
                "move_status": "inferred",
                "current_signal": "合规要求提高",
                "inferred_next_move": "可能增加合规投入",
                "rationale": "维持准入资格",
                "evidence_ids": [evidence_id],
                "uncertainty": "企业投入信息不足",
            }
        ],
        "competition_impact": "合规能力差异可能扩大",
        "business_model_impact": "合规成本可能影响成本结构",
        "customer_demand_impact": "客户可能更加重视合规证明",
        "company_exposure": None,
        "leading_indicators": [
            {
                "name": "监管文件变化",
                "definition": "新增或修订的准入要求",
                "direction_to_watch": "threshold",
                "trigger_condition": "出现新的正式准入要求",
                "data_source": "监管机构网站",
                "monitoring_frequency": "event-driven",
            }
        ],
        "falsification_conditions": ["监管要求明显放宽", "准入周期持续缩短"],
        "uncertainties": ["不同产品分类差异"],
        "evidence_ids": [evidence_id],
        "finding_ids": [finding_id],
        "counter_evidence_ids": [],
        "confidence_note": "当前仅有一个独立来源",
    }
    scenarios = []
    for scenario_type, scenario_id in (
        ("baseline", "SCN-BASE"),
        ("accelerated", "SCN-ACC"),
        ("blocked", "SCN-BLOCK"),
    ):
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "scenario_type": scenario_type,
                "title": scenario_type,
                "narrative": "基于当前信号的定性情景。",
                "trigger_conditions": ["监管方向保持连续"],
                "expected_outcomes": ["市场进入条件变化"],
                "trend_ids": ["TRD-01"],
                "evidence_ids": [evidence_id],
                "finding_ids": [finding_id],
                "leading_indicators": ["监管文件变化"],
                "falsification_conditions": ["监管方向发生逆转"],
                "likelihood_label": "moderate",
            }
        )
    return {
        "forecast_mode": "general",
        "trends": [trend],
        "scenarios": scenarios,
        "monitoring_priorities": ["监管文件变化"],
        "forecast_gaps": ["缺少企业一手信号"],
    }


class FakeModel:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = 0

    def complete_json(self, messages, *, enable_thinking=False):
        self.calls += 1
        return self.response, ModelResponse(content="{}", model="fake")


class InvalidJsonThenValidModel(FakeModel):
    def complete_json(self, messages, *, enable_thinking=False):
        self.calls += 1
        if self.calls == 1:
            raise ProviderError("Modelhub did not return valid JSON")
        return self.response, ModelResponse(content="{}", model="fake")


def test_future_confidence_is_computed_by_system() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    service = FutureIntelligenceService(
        FakeModel(payload(evidence.evidence_id, finding.finding_id)),
        load_active_sop(),
    )

    future = service.generate(project, evidence_artifact, analysis)

    assert len(future.trends) == 1
    assert len(future.scenarios) == 3
    assert future.trends[0].confidence.evidence_quality == 90
    assert future.trends[0].confidence.enterprise_signal_support is None
    assert set(future.methodology.rule_ids) >= {
        "SUL-SIZE-003",
        "SUL-DRIVER-003",
        "SUL-EVIDENCE-002",
        "SUL-FUTURE-001",
        "SUL-FUTURE-002",
        "SUL-GOV-001",
    }


def test_quick_pipeline_can_generate_future_draft_before_gate_two() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    pending_modules = [
        module.model_copy(
            update={
                "findings": [
                    item.model_copy(update={"review_status": AnalysisReviewStatus.NEEDS_REVIEW})
                    for item in module.findings
                ]
            }
        )
        for module in analysis.modules
    ]
    pending_analysis = analysis.model_copy(
        update={"modules": pending_modules, "human_confirmed": False}
    )
    service = FutureIntelligenceService(
        FakeModel(payload(evidence.evidence_id, finding.finding_id)),
        load_active_sop(),
    )

    future = service.generate(
        project,
        evidence_artifact,
        pending_analysis,
        allow_pending_findings=True,
    )

    assert future.human_confirmed is False
    assert future.input_finding_ids == [finding.finding_id]


def test_future_rejects_unknown_finding_reference() -> None:
    project, evidence_artifact, analysis, evidence, _ = fixtures()
    model = FakeModel(payload(evidence.evidence_id, "FND-unknown"))
    service = FutureIntelligenceService(model, load_active_sop())

    with pytest.raises(FutureIntelligenceError, match="未知或未接受"):
        service.generate(project, evidence_artifact, analysis)

    assert model.calls == 2


def test_future_discards_unsupported_player_move_without_blocking_forecast() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    generated = payload(evidence.evidence_id, finding.finding_id)
    generated["trends"][0]["player_moves"][0]["evidence_ids"] = ["EVD-unknown"]
    model = FakeModel(generated)

    future = FutureIntelligenceService(model, load_active_sop()).generate(
        project, evidence_artifact, analysis
    )

    assert model.calls == 1
    assert future.trends[0].player_moves == []
    assert any("行动推演因无可验证证据引用而未采用" in gap for gap in future.forecast_gaps)


def test_future_keeps_valid_part_of_mixed_nested_references() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    generated = payload(evidence.evidence_id, finding.finding_id)
    generated["trends"][0]["player_moves"][0]["evidence_ids"] = [
        "EVD-unknown",
        evidence.evidence_id,
        evidence.evidence_id,
    ]
    generated["trends"][0]["observed_signals"][0]["finding_ids"] = [
        "FND-unknown",
        finding.finding_id,
    ]

    future = FutureIntelligenceService(
        FakeModel(generated), load_active_sop()
    ).generate(project, evidence_artifact, analysis)

    assert future.trends[0].player_moves[0].evidence_ids == [evidence.evidence_id]
    assert future.trends[0].observed_signals[0].finding_ids == [finding.finding_id]


def test_future_still_rejects_forecast_with_no_grounded_top_level_reference() -> None:
    project, evidence_artifact, analysis, _, finding = fixtures()
    invalid = payload("EVD-unknown", finding.finding_id)

    with pytest.raises(FutureIntelligenceError, match="Evidence"):
        FutureIntelligenceService(FakeModel(invalid), load_active_sop()).generate(
            project, evidence_artifact, analysis
        )


def test_future_prompt_contains_sullivan_development_direction_rules() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()

    class CapturingModel(FakeModel):
        messages = None

        def complete_json(self, messages, *, enable_thinking=False):
            self.messages = messages
            return super().complete_json(messages, enable_thinking=enable_thinking)

    model = CapturingModel(payload(evidence.evidence_id, finding.finding_id))
    FutureIntelligenceService(model, load_active_sop()).generate(
        project, evidence_artifact, analysis
    )

    prompt = "\n".join(message.content for message in model.messages)
    assert "过去5至10年" in prompt
    assert "下游需求" in prompt
    assert "商业模式与渠道" in prompt
    assert "玩家布局" in prompt
    assert "结构性、周期性和一次性" in prompt


def test_future_retries_one_invalid_json_response() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    model = InvalidJsonThenValidModel(payload(evidence.evidence_id, finding.finding_id))
    future = FutureIntelligenceService(model, load_active_sop()).generate(
        project, evidence_artifact, analysis
    )

    assert model.calls == 2
    assert len(future.scenarios) == 3


def test_future_rejects_unvalidated_probability_field() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    invalid = payload(evidence.evidence_id, finding.finding_id)
    invalid["scenarios"][0]["probability"] = 0.72
    model = FakeModel(invalid)

    with pytest.raises(FutureIntelligenceError, match="精确概率"):
        FutureIntelligenceService(model, load_active_sop()).generate(
            project, evidence_artifact, analysis
        )


def test_future_review_gate_requires_trends_and_baseline() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    service = FutureIntelligenceService(
        FakeModel(payload(evidence.evidence_id, finding.finding_id)),
        load_active_sop(),
    )
    future = service.generate(project, evidence_artifact, analysis)
    assert forecast_gate_reasons(future)

    for trend in list(future.trends):
        future = review_forecast_item(
            future, trend.trend_id, ForecastReviewStatus.ACCEPTED, "reviewed"
        )
    for scenario in list(future.scenarios):
        future = review_forecast_item(
            future, scenario.scenario_id, ForecastReviewStatus.ACCEPTED, "reviewed"
        )
    assert forecast_gate_reasons(future) == []


def test_trend_forecast_workspace_renders_from_session_artifacts() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    future = FutureIntelligenceService(
        FakeModel(payload(evidence.evidence_id, finding.finding_id)),
        load_active_sop(),
    ).generate(project, evidence_artifact, analysis)
    project = project.model_copy(
        update={
            "evidence_collection_artifact": evidence_artifact,
            "industry_analysis_artifact": analysis,
            "future_intelligence_artifact": future,
        }
    )

    app = AppTest.from_file("app.py")
    app.session_state[PROJECT_KEY] = project.model_dump(mode="json")
    app.session_state[ACTIVE_PAGE_KEY] = "trend_forecast"
    app.run(timeout=10)

    assert not app.exception
    assert any("Forecast Overview" in item.value for item in app.subheader)
    assert any(button.label == "接受趋势" for button in app.button)
    assert any(button.label == "接受情景" for button in app.button)


def test_general_report_is_composed_only_after_both_gates() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    future = FutureIntelligenceService(
        FakeModel(payload(evidence.evidence_id, finding.finding_id)),
        load_active_sop(),
    ).generate(project, evidence_artifact, analysis)
    for trend in list(future.trends):
        future = review_forecast_item(
            future, trend.trend_id, ForecastReviewStatus.ACCEPTED, "Gate 2"
        )
    for scenario in list(future.scenarios):
        future = review_forecast_item(
            future, scenario.scenario_id, ForecastReviewStatus.ACCEPTED, "Gate 2"
        )
    future = future.model_copy(update={"human_confirmed": True})
    reviewed_project = project.model_copy(
        update={
            "evidence_collection_artifact": evidence_artifact,
            "industry_analysis_artifact": analysis,
            "future_intelligence_artifact": future,
        }
    )

    report = generate_general_report(reviewed_project)

    assert "本报告依据经人工确认的市场口径" in report.markdown
    assert evidence.evidence_id in report.markdown
    assert report.source_count == 1
    assert "➡" not in report.markdown
    assert "👉" not in report.markdown
    assert not any(line.startswith("- ") for line in report.markdown.splitlines())


def test_report_semantically_checks_original_prompt_coverage() -> None:
    project, evidence_artifact, analysis, evidence, finding = fixtures()
    future = FutureIntelligenceService(
        FakeModel(payload(evidence.evidence_id, finding.finding_id)),
        load_active_sop(),
    ).generate(project, evidence_artifact, analysis)
    for trend in list(future.trends):
        future = review_forecast_item(
            future, trend.trend_id, ForecastReviewStatus.ACCEPTED, "Gate 2"
        )
    for scenario in list(future.scenarios):
        future = review_forecast_item(
            future, scenario.scenario_id, ForecastReviewStatus.ACCEPTED, "Gate 2"
        )
    future = future.model_copy(update={"human_confirmed": True})
    reviewed_project = project.model_copy(
        update={
            "evidence_collection_artifact": evidence_artifact,
            "industry_analysis_artifact": analysis,
            "future_intelligence_artifact": future,
        }
    )
    trend = future.trends[0]
    coverage_payload = {
        "items": [
            {
                "question_index": 0,
                "coverage_status": "answered",
                "evidence_ids": [evidence.evidence_id],
                "finding_ids": [finding.finding_id],
                "trend_ids": [trend.trend_id],
                "note": "已批准判断和趋势共同回答该问题。",
            }
        ]
    }

    report = ReportGenerationService(FakeModel(coverage_payload)).generate(reviewed_project)

    assert report.prompt_coverage[0].coverage_status == "answered"
    assert "对原始研究问题的回应" in report.markdown
    assert report.unresolved_prompt_questions == []


def test_approved_evidence_reaches_downloadable_report_end_to_end() -> None:
    project, evidence_artifact, _, evidence, _ = fixtures()
    modules = []
    for module_id in EXPECTED_MODULES:
        dimensions = None
        factor_fields = {}
        if module_id == "market_value_chain":
            dimensions = {"value_chain_position": "市场准入"}
        elif module_id == "competitive_landscape":
            dimensions = {
                "relationship_type": "benchmark",
                "comparison_basis": "同一监管环境",
            }
        elif module_id == "drivers_constraints":
            dimensions = {}
            factor_fields = {
                "factor_role": "constraint",
                "impact_direction": "negative",
            }
        modules.append(
            {
                "module_id": module_id,
                "title": module_id,
                "executive_summary": "当前证据支持审慎的行业判断。",
                "findings": [
                    {
                        "subject": "中国分子诊断市场",
                        "finding_type": "analyst_inference",
                        "statement": "监管准入构成当前市场进入条件。",
                        "mechanism": "准入要求增加参与者的合规资源需求。",
                        "evidence_ids": [evidence.evidence_id],
                        "counter_evidence_ids": None,
                        "comparison_dimensions": dimensions,
                        **factor_fields,
                        "confidence": 0.8,
                        "scope": "中国分子诊断市场",
                        "uncertainty": "不同产品分类存在差异",
                        "boundary_condition": "不适用于纯科研产品",
                    }
                ],
                "evidence_gaps": ["仍需更多独立来源"],
                "rejected_questions": [],
            }
        )
    analysis = IndustryAnalysisService(
        FakeModel({"modules": modules}), load_active_sop()
    ).generate(project, evidence_artifact)
    for item in list(analysis.findings):
        analysis = review_analysis_finding(
            analysis,
            item.finding_id,
            AnalysisReviewStatus.ACCEPTED,
            "端到端测试审核",
        )
    analysis = analysis.model_copy(update={"human_confirmed": True})

    anchor_finding = analysis.findings[0]
    future = FutureIntelligenceService(
        FakeModel(payload(evidence.evidence_id, anchor_finding.finding_id)),
        load_active_sop(),
    ).generate(project, evidence_artifact, analysis)
    for item in [*future.trends, *future.scenarios]:
        item_id = item.trend_id if hasattr(item, "trend_id") else item.scenario_id
        future = review_forecast_item(
            future,
            item_id,
            ForecastReviewStatus.ACCEPTED,
            "端到端测试审核",
        )
    future = future.model_copy(update={"human_confirmed": True})
    reviewed_project = project.model_copy(
        update={
            "evidence_collection_artifact": evidence_artifact,
            "industry_analysis_artifact": analysis,
            "future_intelligence_artifact": future,
        }
    )
    coverage_payload = {
        "items": [
            {
                "question_index": 0,
                "coverage_status": "answered",
                "evidence_ids": [evidence.evidence_id],
                "finding_ids": [anchor_finding.finding_id],
                "trend_ids": [future.trends[0].trend_id],
                "note": "已批准证据、判断和趋势共同回答该问题。",
            }
        ]
    }
    report = ReportGenerationService(FakeModel(coverage_payload)).generate(
        reviewed_project
    )
    export = project_report_context(
        reviewed_project,
        title=report.title,
        markdown=report.markdown,
        report_status="端到端测试报告",
        generated_at=report.generated_at,
    )

    assert report.accepted_evidence_ids == [evidence.evidence_id]
    assert build_report_docx(export).startswith(b"PK")
    assert build_report_pdf(export).startswith(b"%PDF")

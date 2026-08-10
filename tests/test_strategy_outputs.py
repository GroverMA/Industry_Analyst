from __future__ import annotations

import re

import pytest

from src.knowledge.sop import load_active_sop
from src.models.analysis import (
    AnalysisFinding,
    AnalysisFindingType,
    AnalysisReviewStatus,
    IndustryAnalysisArtifact,
    IndustryAnalysisModule,
)
from src.models.enterprise import (
    EnterpriseEvidenceCategory,
    EnterpriseEvidenceItem,
    EnterpriseReviewStatus,
    EnterpriseSensingArtifact,
    EnterpriseStatementType,
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
from src.models.future import (
    ForecastConfidence,
    ForecastReviewStatus,
    FutureIntelligenceArtifact,
    FutureScenario,
    FutureTrend,
    LeadingIndicator,
    ObservedSignal,
    ScenarioType,
    TrendCategory,
)
from src.models.report import GeneralReportArtifact
from src.models.research import MethodologyTrace
from src.models.strategy import StrategyReviewStatus
from src.providers.base import ModelResponse, ProviderError
from src.services.action_planning import (
    ActionPlanningError,
    ActionPlanningService,
    confirm_action_plan,
    review_action,
)
from src.services.company_assessment import (
    CompanyAssessmentError,
    CompanyAssessmentService,
    confirm_scorecard,
    review_score_dimension,
)
from src.services.strategy_report import generate_enterprise_decision_report
from src.state.project import ProjectState


class FakeModel:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete_json(self, messages, *, enable_thinking=False):
        self.calls += 1
        return self.payload, ModelResponse(content="{}", model="fake")


class FailingModel:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, messages, *, enable_thinking=False):
        self.calls += 1
        raise ProviderError("provider returned unusable structured output")


class LegacyScoreDimension:
    """Shape persisted before market-position and strategic-gap fields existed."""

    def __init__(self, item) -> None:
        for field in (
            "dimension_id",
            "title",
            "weight",
            "score",
            "score_rationale",
            "strengths",
            "gaps",
            "risks",
            "confidence",
            "review_status",
        ):
            setattr(self, field, getattr(item, field))

    def model_copy(self, *, update: dict):
        clone = LegacyScoreDimension.__new__(LegacyScoreDimension)
        clone.__dict__ = {**self.__dict__, **update}
        return clone


def eligible_project() -> tuple[ProjectState, str, str, str, str]:
    trace = MethodologyTrace(
        sop_id="test",
        sop_name="Test SOP",
        sop_version="1",
        sop_hash="abc",
        rule_ids=["TEST"],
    )
    sources = []
    evidence_items = []
    for index, statement in enumerate(
        ("工作流一体化需求正在增加。", "头部企业持续投入自动化和临床证据。"),
        start=1,
    ):
        source = EvidenceSource(
            task_id="T01",
            discovery_query="diagnostics",
            title=f"Official source {index}",
            url=f"https://example.gov.cn/report-{index}",
            domain="example.gov.cn",
            source_tier=SourceTier.A,
            tier_reason="official",
            transport="rest",
            crawled=True,
        )
        sources.append(source)
        evidence_items.append(
            EvidenceItem(
                task_id="T01",
                source_id=source.source_id,
                kind=EvidenceKind.FACT,
                statement=statement,
                supporting_excerpt=statement,
                geographic_scope="中国",
                market_scope="分子诊断",
                supports_or_challenges="supports",
                model_confidence=0.9,
                qa_score=90 - index,
                review_status=EvidenceReviewStatus.ACCEPTED,
            )
        )
    evidence = EvidenceCollectionArtifact(
        research_plan_id="plan",
        task_runs=[
            TaskEvidenceRun(
                task_id="T01",
                task_title="市场与竞争",
                queries_used=["diagnostics"],
                sources=sources,
                evidence=evidence_items,
            )
        ],
        human_confirmed=True,
    )
    finding = AnalysisFinding(
        subject="竞争能力",
        finding_type=AnalysisFindingType.ANALYST_INFERENCE,
        statement="工作流与临床证据正在成为重要竞争条件。",
        mechanism="客户采购标准从单品性能扩展到整体交付。",
        evidence_ids=[item.evidence_id for item in evidence_items],
        confidence=0.8,
        scope="中国分子诊断",
        uncertainty="细分市场差异",
        boundary_condition="科研市场除外",
        review_status=AnalysisReviewStatus.ACCEPTED,
    )
    analysis = IndustryAnalysisArtifact(
        evidence_collection_id=evidence.artifact_id,
        input_evidence_ids=[item.evidence_id for item in evidence_items],
        modules=[
            IndustryAnalysisModule(
                module_id=value,
                title=value,
                executive_summary="summary",
                findings=[finding] if index == 0 else [],
            )
            for index, value in enumerate(
                ("market_value_chain", "market_status", "competitive_landscape", "drivers_constraints", "commercial_logic")
            )
        ],
        methodology=trace,
        human_confirmed=True,
    )
    signal = ObservedSignal(
        signal_type="customer",
        description="工作流需求增加",
        evidence_ids=[evidence_items[0].evidence_id],
        finding_ids=[finding.finding_id],
        direction="supports",
    )
    indicator = LeadingIndicator(
        name="一体化项目占比",
        definition="一体化方案项目数/新增项目数",
        direction_to_watch="up",
        trigger_condition="连续两个季度超过30%",
        data_source="招投标与CRM",
        monitoring_frequency="quarterly",
    )
    confidence = ForecastConfidence(
        evidence_quality=85,
        source_diversity=70,
        signal_consistency=80,
        causal_clarity=75,
        player_commitment=70,
        time_distance=75,
        counter_evidence_resilience=60,
        enterprise_signal_support=80,
        overall=75,
    )
    trend = FutureTrend(
        title="工作流解决方案竞争",
        category=TrendCategory.BUSINESS_MODEL,
        forecast_horizon="2026-2028",
        forecast_year_end=2028,
        forecast_statement="竞争可能从单项试剂转向工作流解决方案。",
        observed_signals=[signal],
        causal_mechanism=["客户复杂度上升", "采购标准变化"],
        assumptions=["客户持续重视周转时间"],
        affected_players=["诊断企业"],
        competition_impact="整合能力重要性提高",
        business_model_impact="服务收入占比可能上升",
        customer_demand_impact="一体化需求提高",
        leading_indicators=[indicator],
        falsification_conditions=["客户重新只按试剂价格采购"],
        uncertainties=["医院等级差异"],
        evidence_ids=[evidence_items[0].evidence_id],
        finding_ids=[finding.finding_id],
        confidence=confidence,
        confidence_note="信号方向一致",
        review_status=ForecastReviewStatus.ACCEPTED,
    )
    scenarios = [
        FutureScenario(
            scenario_type=scenario_type,
            title=scenario_type.value,
            narrative="定性情景",
            trigger_conditions=["客户采购标准变化"],
            expected_outcomes=["竞争能力分化"],
            trend_ids=[trend.trend_id],
            evidence_ids=[evidence_items[0].evidence_id],
            finding_ids=[finding.finding_id],
            leading_indicators=["一体化项目占比"],
            falsification_conditions=["指标方向逆转"],
            likelihood_label="moderate",
            review_status=ForecastReviewStatus.ACCEPTED,
        )
        for scenario_type in (ScenarioType.BASELINE, ScenarioType.ACCELERATED, ScenarioType.BLOCKED)
    ]
    future = FutureIntelligenceArtifact(
        industry_analysis_id=analysis.artifact_id,
        evidence_collection_id=evidence.artifact_id,
        input_evidence_ids=[item.evidence_id for item in evidence_items],
        input_finding_ids=[finding.finding_id],
        forecast_mode="enterprise",
        trends=[trend],
        scenarios=scenarios,
        monitoring_priorities=["一体化项目占比"],
        methodology=trace,
        human_confirmed=True,
    )
    enterprise_items = [
        EnterpriseEvidenceItem(
            title="Channel strength",
            category=EnterpriseEvidenceCategory.SALES_CHANNEL,
            statement_type=EnterpriseStatementType.OBSERVATION,
            content="模拟企业拥有医院渠道，但方案销售能力有限。",
            source_owner="Demo sales lead",
            strategic_relevance="影响市场进入与商业化。",
            review_status=EnterpriseReviewStatus.ACCEPTED,
        ),
        EnterpriseEvidenceItem(
            title="R&D constraint",
            category=EnterpriseEvidenceCategory.RESEARCH_DEVELOPMENT,
            statement_type=EnterpriseStatementType.FACT,
            content="模拟研发资源主要集中在PCR平台。",
            source_owner="Demo R&D lead",
            strategic_relevance="影响创新与未来适配。",
            review_status=EnterpriseReviewStatus.ACCEPTED,
        ),
    ]
    enterprise = EnterpriseSensingArtifact(
        project_id="project",
        target_company_snapshot="Demo Diagnostics",
        strategy_objective_snapshot="进入工作流解决方案市场并保护PCR现金流",
        entries=enterprise_items,
        consent_to_model_processing=True,
        public_demo_acknowledged=True,
        human_confirmed=True,
    )
    project = ProjectState(
        project_id="project",
        project_name="Demo Strategy",
        industry="分子诊断",
        region="中国",
        target_company="Demo Diagnostics",
        company_strategy_enabled=True,
        company_strategy_objective="进入工作流解决方案市场并保护PCR现金流",
        research_objective="研究竞争格局、趋势与战略行动",
        time_horizon="2026-2030",
        evidence_collection_artifact=evidence,
        industry_analysis_artifact=analysis,
        future_intelligence_artifact=future,
        enterprise_sensing_artifact=enterprise,
        general_report_artifact=GeneralReportArtifact(title="General", markdown="# General"),
    )
    return (
        project,
        evidence_items[0].evidence_id,
        enterprise_items[0].enterprise_evidence_id,
        trend.trend_id,
        scenarios[0].scenario_id,
    )


def scorecard_payload(evidence_id: str, enterprise_id: str) -> dict:
    dimension_ids = (
        "market_position",
        "product_competitiveness",
        "commercialization_channel",
        "operations_economics",
        "innovation_future_fit",
        "organization_execution",
    )
    return {
        "benchmarks": [
            {
                "name": "Evidence-backed strategic threshold",
                "benchmark_type": "strategic_threshold",
                "rationale": "客户采购标准变化形成能力阈值",
                "evidence_ids": [evidence_id],
            }
        ],
        "dimensions": [
            {
                "dimension_id": dimension_id,
                "score_components": {
                    "current_capability": 4,
                    "benchmark_position": 4,
                    "strategic_fit": 4,
                    "future_readiness": 4,
                },
                "score_rationale": "企业渠道基础支持目标，但仍需能力补足。",
                "benchmark_names": ["Evidence-backed strategic threshold"],
                "external_evidence_ids": [evidence_id],
                "enterprise_evidence_ids": [enterprise_id],
                "strengths": ["现有渠道"],
                "gaps": ["方案销售"],
                "risks": ["资源分散"],
                "industry_relevance": "工作流解决方案正在成为行业竞争的重要维度。",
                "current_market_position": "企业具备医院渠道基础，但方案销售与交付能力仍有限。",
                "target_position": "形成可复制的工作流解决方案销售与交付能力。",
                "strategic_gap": "现有单产品销售能力与目标方案化能力之间仍有差距。",
                "strategic_fit_explanation": "与进入工作流解决方案市场的目标直接相关。",
                "uncertainty": "企业样本有限",
            }
            for dimension_id in dimension_ids
        ],
        "overall_assessment": "具备进入基础，但需要分阶段验证。",
        "strategic_advantages": ["渠道基础"],
        "critical_gaps": ["方案交付能力"],
        "cross_dimension_risks": ["资源分散"],
    }


def action_payload(evidence_id: str, enterprise_id: str, trend_id: str, scenario_id: str) -> dict:
    actions = []
    for index, priority in enumerate(("critical", "high", "medium"), start=1):
        actions.append(
            {
                "title": f"分阶段验证行动{index}",
                "rationale": "利用渠道基础验证工作流需求，并控制现金流风险。",
                "strategic_objective": "进入工作流解决方案市场并保护PCR现金流",
                "priority": priority,
                "owner_role": "业务负责人",
                "timing": f"第{index}阶段",
                "resources": ["跨职能项目组", "验证预算"],
                "dependencies": ["目标客户确认"],
                "kpis": [
                    {
                        "name": "试点转化率",
                        "kpi_type": "leading",
                        "definition": "进入试点客户/目标客户",
                        "target": ">=30%",
                        "timing": "季度",
                        "data_source": "CRM",
                    },
                    {
                        "name": "新增毛利",
                        "kpi_type": "outcome",
                        "definition": "新方案贡献毛利",
                        "target": "达到管理层门槛",
                        "timing": "年度",
                        "data_source": "财务系统",
                    },
                ],
                "risks": ["资源分散"],
                "mitigations": ["分阶段拨款"],
                "stop_conditions": ["连续两个季度低于试点转化阈值"],
                "score_dimension_ids": ["market_position"],
                "evidence_ids": [evidence_id],
                "enterprise_evidence_ids": [enterprise_id],
                "trend_ids": [trend_id],
                "scenario_ids": [scenario_id],
                "uncertainty": "客户需求转化速度",
            }
        )
    return {
        "actions": actions,
        "sequencing_logic": ["先验证需求，再扩张投入"],
        "rejected_options": ["立即全面扩张：证据不足"],
        "portfolio_risks": ["多项目争夺研发资源"],
    }


def test_score_is_calculated_and_not_accepted_from_model() -> None:
    project, evidence_id, enterprise_id, _, _ = eligible_project()
    payload = scorecard_payload(evidence_id, enterprise_id)
    payload["dimensions"][0]["score"] = 1
    artifact = CompanyAssessmentService(FakeModel(payload), load_active_sop()).generate(project)

    assert artifact.weighted_score == 80.0
    assert artifact.weighted_benchmark_score == 80.0
    assert artifact.weighted_gap == 0.0
    assert artifact.scored_weight == 1.0
    assert all(item.score == 80.0 for item in artifact.dimensions)
    assert all(item.benchmark_score == 80.0 for item in artifact.dimensions)
    assert all(item.benchmark_gap == 0.0 for item in artifact.dimensions)
    assert all(item.market_position_label == "达到或接近市场基准" for item in artifact.dimensions)
    assert all(item.confidence > 0 for item in artifact.dimensions)


def test_missing_company_evidence_makes_dimension_unscored_not_neutral() -> None:
    project, evidence_id, enterprise_id, _, _ = eligible_project()
    payload = scorecard_payload(evidence_id, enterprise_id)
    payload["dimensions"][0]["enterprise_evidence_ids"] = []
    payload["dimensions"][0]["unscored_reason"] = "缺少该维度企业资料"
    artifact = CompanyAssessmentService(FakeModel(payload), load_active_sop()).generate(project)

    assert artifact.dimensions[0].score is None
    assert artifact.dimensions[0].unscored_reason == "缺少该维度企业资料"
    assert artifact.weighted_score == 80.0


def test_scorecard_prunes_unknown_citations_and_preserves_strategy_gap() -> None:
    project, evidence_id, enterprise_id, trend_id, _ = eligible_project()
    payload = scorecard_payload(evidence_id, enterprise_id)
    payload["benchmarks"][0]["evidence_ids"].append("EVD-stale-or-hallucinated")
    for dimension in payload["dimensions"]:
        dimension["external_evidence_ids"].append("EVD-stale-or-hallucinated")
        dimension["enterprise_evidence_ids"].append("ENT-stale-or-hallucinated")
        dimension["linked_trend_ids"] = [trend_id, "TRD-stale-or-hallucinated"]

    artifact = CompanyAssessmentService(FakeModel(payload), load_active_sop()).generate(project)

    assert artifact.weighted_score == 80.0
    assert artifact.benchmarks[0].evidence_ids == [evidence_id]
    assert all(item.external_evidence_ids == [evidence_id] for item in artifact.dimensions)
    assert all(item.enterprise_evidence_ids == [enterprise_id] for item in artifact.dimensions)
    assert all(item.linked_trend_ids == [trend_id] for item in artifact.dimensions)
    assert all(item.current_market_position for item in artifact.dimensions)
    assert all(item.target_position == "形成可复制的工作流解决方案销售与交付能力。" for item in artifact.dimensions)
    assert all(item.strategic_gap for item in artifact.dimensions)


def test_scorecard_recovers_when_all_model_benchmark_ids_are_unknown() -> None:
    project, evidence_id, enterprise_id, _, _ = eligible_project()
    payload = scorecard_payload(evidence_id, enterprise_id)
    payload["benchmarks"][0]["evidence_ids"] = ["EVD-unknown"]

    artifact = CompanyAssessmentService(FakeModel(payload), load_active_sop()).generate(project)

    assert artifact.weighted_score == 80.0
    assert artifact.benchmarks[0].name == "战略目标能力阈值"
    assert artifact.benchmarks[0].evidence_ids == [evidence_id]


def test_scorecard_and_action_plan_require_human_review() -> None:
    project, evidence_id, enterprise_id, trend_id, scenario_id = eligible_project()
    scorecard = CompanyAssessmentService(
        FakeModel(scorecard_payload(evidence_id, enterprise_id)), load_active_sop()
    ).generate(project)
    with pytest.raises(CompanyAssessmentError, match="待审核"):
        confirm_scorecard(scorecard)
    for item in scorecard.dimensions:
        scorecard = review_score_dimension(
            scorecard, item.dimension_id, StrategyReviewStatus.ACCEPTED
        )
    scorecard = confirm_scorecard(scorecard)
    project = project.model_copy(update={"company_scorecard_artifact": scorecard})

    action_plan = ActionPlanningService(
        FakeModel(action_payload(evidence_id, enterprise_id, trend_id, scenario_id)),
        load_active_sop(),
    ).generate(project)
    with pytest.raises(ActionPlanningError, match="待审核"):
        confirm_action_plan(action_plan)
    for item in action_plan.actions:
        action_plan = review_action(action_plan, item.action_id, StrategyReviewStatus.ACCEPTED)
    action_plan = confirm_action_plan(action_plan)

    assert action_plan.human_confirmed is True
    assert all({kpi.kpi_type.value for kpi in item.kpis} == {"leading", "outcome"} for item in action_plan.actions)
    assert {item.timing for item in action_plan.actions} == {"短期", "长期"}

    project = project.model_copy(update={"action_plan_artifact": action_plan})
    report = generate_enterprise_decision_report(project)
    assert "公司能力评分" in report.markdown
    assert "市场基准分" in report.markdown
    assert "基准差距" in report.markdown
    assert "达到或接近市场基准" in report.markdown
    assert "公司当前市场位置" in report.markdown
    assert "战略目标状态" in report.markdown
    assert "现有单产品销售能力与目标方案化能力之间仍有差距" in report.markdown
    assert "停止、调整或转向" in report.markdown
    assert re.search(r"### \d+\.\d+ 战略优势\n\n- 渠道基础。", report.markdown)
    assert re.search(r"### \d+\.\d+ 关键差距\n\n- 方案交付能力。", report.markdown)
    assert re.search(r"### \d+\.\d+ 推进顺序\n\n- 先验证需求，再扩张投入。", report.markdown)
    assert "- 立即全面扩张：当前信息基础尚不支持。" in report.markdown
    enterprise_sections = [
        "企业战略意图与决策框架",
        "公司能力评分",
        "战略行动计划",
        "推进顺序及组合风险",
        "人工审核及责任边界",
    ]
    assert [report.markdown.index(title) for title in enterprise_sections] == sorted(
        report.markdown.index(title) for title in enterprise_sections
    )
    assert not re.search(r"\b(?:EVD|FND|TRD|SCN|ENT|DIM|ACT)-[A-Za-z0-9_-]+\b", report.markdown)
    assert enterprise_id not in report.markdown
    assert evidence_id not in report.markdown


def test_action_plan_prunes_unknown_trace_ids_and_keeps_pipeline_running() -> None:
    project, evidence_id, enterprise_id, trend_id, scenario_id = eligible_project()
    scorecard = CompanyAssessmentService(
        FakeModel(scorecard_payload(evidence_id, enterprise_id)), load_active_sop()
    ).generate(project)
    for item in scorecard.dimensions:
        scorecard = review_score_dimension(scorecard, item.dimension_id, StrategyReviewStatus.ACCEPTED)
    project = project.model_copy(update={"company_scorecard_artifact": confirm_scorecard(scorecard)})
    payload = action_payload(evidence_id, enterprise_id, trend_id, scenario_id)
    payload["actions"][0]["evidence_ids"] = ["EVD-unknown"]

    artifact = ActionPlanningService(FakeModel(payload), load_active_sop()).generate(project)

    assert artifact.actions[0].evidence_ids == [evidence_id]
    assert artifact.actions[0].score_dimension_ids == ["market_position"]
    assert artifact.actions[0].enterprise_evidence_ids == [enterprise_id]
    assert artifact.actions[0].trend_ids == [trend_id]


def test_build_first_strategy_pipeline_never_leaves_scorecard_or_action_plan_blank() -> None:
    project, _, _, _, _ = eligible_project()
    failing_company_model = FailingModel()
    scorecard = CompanyAssessmentService(failing_company_model, load_active_sop()).generate(project)

    assert failing_company_model.calls == 2
    assert len(scorecard.dimensions) == 6
    assert all(item.current_market_position for item in scorecard.dimensions)
    assert all(item.target_position == project.company_strategy_objective for item in scorecard.dimensions)
    assert all(item.strategic_gap for item in scorecard.dimensions)

    for item in scorecard.dimensions:
        scorecard = review_score_dimension(
            scorecard, item.dimension_id, StrategyReviewStatus.ACCEPTED
        )
    scorecard = confirm_scorecard(scorecard)
    project = project.model_copy(update={"company_scorecard_artifact": scorecard})

    failing_action_model = FailingModel()
    plan = ActionPlanningService(failing_action_model, load_active_sop()).generate(project)

    assert failing_action_model.calls == 2
    assert len(plan.actions) >= 3
    assert {item.timing for item in plan.actions} == {"短期", "长期"}
    assert all(item.rationale and item.score_dimension_ids for item in plan.actions)
    assert all(item.strategic_objective == project.company_strategy_objective for item in plan.actions)


def test_review_first_strategy_pipeline_migrates_legacy_scorecard_dimensions() -> None:
    project, evidence_id, enterprise_id, _, _ = eligible_project()
    scorecard = CompanyAssessmentService(
        FakeModel(scorecard_payload(evidence_id, enterprise_id)), load_active_sop()
    ).generate(project)
    for item in scorecard.dimensions:
        scorecard = review_score_dimension(
            scorecard, item.dimension_id, StrategyReviewStatus.ACCEPTED
        )
    scorecard = confirm_scorecard(scorecard)
    legacy_scorecard = scorecard.model_copy(
        update={"dimensions": [LegacyScoreDimension(item) for item in scorecard.dimensions]}
    )
    project = project.model_copy(update={"company_scorecard_artifact": legacy_scorecard})

    plan = ActionPlanningService(FailingModel(), load_active_sop()).generate(project)

    assert len(plan.actions) >= 3
    assert {item.timing for item in plan.actions} == {"短期", "长期"}
    assert all("战略目标" in item.rationale or "目标状态" in item.rationale for item in plan.actions)


def test_project_snapshot_round_trips_strategy_artifacts() -> None:
    project, evidence_id, enterprise_id, _, _ = eligible_project()
    scorecard = CompanyAssessmentService(
        FakeModel(scorecard_payload(evidence_id, enterprise_id)), load_active_sop()
    ).generate(project)
    restored = ProjectState.model_validate_json(
        project.model_copy(update={"company_scorecard_artifact": scorecard}).model_dump_json()
    )
    assert restored.company_scorecard_artifact == scorecard

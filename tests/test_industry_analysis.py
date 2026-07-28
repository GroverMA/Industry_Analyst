from __future__ import annotations

from src.knowledge.sop import load_active_sop
from src.models.analysis import AnalysisReviewStatus
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
)
from src.providers.base import ModelResponse, ProviderError
from src.services.industry_analysis import (
    EXPECTED_MODULES,
    IndustryAnalysisService,
    analysis_gate_reasons,
    review_analysis_finding,
)
from src.state.project import ProjectState


def project() -> ProjectState:
    trace = MethodologyTrace(
        sop_id="test", sop_name="Test SOP", sop_version="1", sop_hash="abc", rule_ids=["TEST"]
    )
    brief = ResearchBriefArtifact(
        decision_statement="研究当前行业结构",
        original_prompt="研究当前行业结构",
        interpreted_intent=ResearchIntent(
            interpreted_objective="研究当前行业结构",
            requested_topics=["发展条件"],
            must_answer_questions=["行业发展的条件是什么？"],
        ),
        market_definition=MarketDefinition(
            core_market="分子诊断",
            product_scope="诊断产品与服务",
            customer_scope="医疗机构",
            geography_scope="中国",
            value_chain_scope="全产业链",
            time_scope="2024-2026",
            inclusions=["临床分子诊断"],
            exclusions=["纯科研产品"],
        ),
        key_questions=["行业发展的条件是什么？"],
        information_gaps=["市场数据"],
        hypotheses=["监管影响市场结构"],
        confidence_note="待证据验证",
        methodology=trace,
        human_confirmed=True,
    )
    return ProjectState(
        project_name="行业研究",
        industry="分子诊断",
        region="中国",
        research_objective="研究当前行业结构",
        time_horizon="2024-2026",
        research_brief_artifact=brief,
    )


def evidence_artifact() -> tuple[EvidenceCollectionArtifact, str, str]:
    source = EvidenceSource(
        task_id="T01",
        discovery_query="query",
        title="监管来源",
        url="https://example.gov.cn/report",
        domain="example.gov.cn",
        source_tier=SourceTier.A,
        tier_reason="government",
        transport="rest",
        crawled=True,
    )
    accepted = EvidenceItem(
        task_id="T01",
        source_id=source.source_id,
        kind=EvidenceKind.FACT,
        statement="当前市场存在明确监管准入要求。",
        supporting_excerpt="市场存在明确监管准入要求",
        geographic_scope="中国",
        market_scope="分子诊断",
        supports_or_challenges="supports",
        model_confidence=0.9,
        qa_score=95,
        review_status=EvidenceReviewStatus.ACCEPTED,
    )
    rejected = accepted.model_copy(
        update={
            "evidence_id": "EVD-rejected",
            "statement": "不应进入模型的证据",
            "review_status": EvidenceReviewStatus.REJECTED,
        }
    )
    run = TaskEvidenceRun(
        task_id="T01",
        task_title="监管",
        queries_used=["query"],
        sources=[source],
        evidence=[accepted, rejected],
    )
    artifact = EvidenceCollectionArtifact(
        research_plan_id="plan",
        task_runs=[run],
        human_confirmed=True,
    )
    return artifact, accepted.evidence_id, rejected.evidence_id


def finding(evidence_id: str, module_id: str) -> dict:
    dimensions = {}
    factor_fields = {}
    if module_id == "competitive_landscape":
        dimensions = {
            "relationship_type": "benchmark",
            "comparison_basis": "同一监管环境",
        }
    if module_id == "drivers_constraints":
        factor_fields = {"factor_role": "constraint", "impact_direction": "negative"}
    if module_id == "market_value_chain":
        dimensions = {"value_chain_position": "市场准入"}
    return {
        "subject": "中国分子诊断市场",
        "finding_type": "analyst_inference",
        "statement": "监管准入是当前市场结构的重要约束。",
        "mechanism": "准入要求影响参与者进入市场的条件。",
        "evidence_ids": [evidence_id],
        "counter_evidence_ids": [],
        "comparison_dimensions": dimensions,
        **factor_fields,
        "confidence": 0.8,
        "scope": "中国分子诊断市场",
        "uncertainty": "缺少不同产品类别的细分证据",
        "boundary_condition": "不适用于非临床科研产品",
    }


def valid_payload(evidence_id: str) -> dict:
    return {
        "modules": [
            {
                "module_id": module_id,
                "title": module_id,
                "executive_summary": "当前证据支持有限的结构判断。",
                "findings": [finding(evidence_id, module_id)],
                "evidence_gaps": ["缺少更多独立来源"],
                "rejected_questions": [],
            }
            for module_id in EXPECTED_MODULES
        ],
        "company_implications": [],
        "cross_module_conflicts": [],
        "overall_evidence_limitations": ["仅有一个来源"],
    }


class FakeModel:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0
        self.last_messages = []

    def complete_json(self, messages, *, enable_thinking=False):
        self.calls += 1
        self.last_messages = messages
        return self.payload, ModelResponse(content="{}", model="fake")


class InvalidJsonThenValidModel(FakeModel):
    def complete_json(self, messages, *, enable_thinking=False):
        self.calls += 1
        self.last_messages = messages
        if self.calls == 1:
            raise ProviderError("Modelhub did not return valid JSON")
        return self.payload, ModelResponse(content="{}", model="fake")


def test_analysis_only_sends_human_accepted_evidence() -> None:
    artifact, accepted_id, rejected_id = evidence_artifact()
    model = FakeModel(valid_payload(accepted_id))
    service = IndustryAnalysisService(model, load_active_sop())

    analysis = service.generate(project(), artifact)

    assert analysis.input_evidence_ids == [accepted_id]
    assert rejected_id not in model.last_messages[-1].content
    assert len(analysis.modules) == 5
    assert set(analysis.methodology.rule_ids) >= {
        "SUL-DEFINE-001",
        "SUL-CHAIN-002",
        "SUL-COMP-001",
        "SUL-DRIVER-003",
        "SUL-GOV-001",
    }


def test_unknown_evidence_id_becomes_explicit_module_gap() -> None:
    artifact, _, _ = evidence_artifact()
    model = FakeModel(valid_payload("EVD-unknown"))
    service = IndustryAnalysisService(model, load_active_sop())

    analysis = service.generate(project(), artifact)

    assert model.calls == 15
    assert all(not module.findings for module in analysis.modules)
    assert all(module.evidence_gaps for module in analysis.modules)


def test_analysis_retries_one_invalid_json_response() -> None:
    artifact, accepted_id, _ = evidence_artifact()
    model = InvalidJsonThenValidModel(valid_payload(accepted_id))
    analysis = IndustryAnalysisService(model, load_active_sop()).generate(
        project(), artifact
    )

    assert model.calls == 6
    assert len(analysis.modules) == 5


def test_analysis_human_review_controls_gate() -> None:
    artifact, accepted_id, _ = evidence_artifact()
    service = IndustryAnalysisService(FakeModel(valid_payload(accepted_id)), load_active_sop())
    analysis = service.generate(project(), artifact)

    assert any("待审核" in reason for reason in analysis_gate_reasons(analysis))
    for item in list(analysis.findings):
        analysis = review_analysis_finding(
            analysis,
            item.finding_id,
            AnalysisReviewStatus.ACCEPTED,
            "已核对证据与机制",
        )
    assert analysis_gate_reasons(analysis) == []


def test_factor_role_accepts_semantic_user_facing_label() -> None:
    artifact, accepted_id, _ = evidence_artifact()
    generated = valid_payload(accepted_id)
    factor = next(
        module for module in generated["modules"]
        if module["module_id"] == "drivers_constraints"
    )["findings"][0]
    factor["factor_role"] = "发展条件"
    factor["impact_direction"] = "mixed"

    analysis = IndustryAnalysisService(
        FakeModel(generated), load_active_sop()
    ).generate(project(), artifact)
    factor_finding = next(
        module for module in analysis.modules
        if module.module_id == "drivers_constraints"
    ).findings[0]

    assert factor_finding.factor_role.value == "enabling_condition"


def test_unclassified_factor_becomes_gap_instead_of_failing_report() -> None:
    artifact, accepted_id, _ = evidence_artifact()
    generated = valid_payload(accepted_id)
    factor_module = next(
        module for module in generated["modules"]
        if module["module_id"] == "drivers_constraints"
    )
    factor_module["findings"][0].pop("factor_role")
    factor_module["findings"][0].pop("impact_direction")

    analysis = IndustryAnalysisService(
        FakeModel(generated), load_active_sop()
    ).generate(project(), artifact)
    factor_result = next(
        module for module in analysis.modules
        if module.module_id == "drivers_constraints"
    )

    assert factor_result.findings == []
    assert any("无法可靠分类" in gap for gap in factor_result.evidence_gaps)


def test_string_null_factor_fields_do_not_block_analysis_assembly() -> None:
    artifact, accepted_id, _ = evidence_artifact()
    generated = valid_payload(accepted_id)
    for module in generated["modules"]:
        if module["module_id"] == "drivers_constraints":
            continue
        for item in module["findings"]:
            item["factor_role"] = "null"
            item["impact_direction"] = "None"

    analysis = IndustryAnalysisService(
        FakeModel(generated), load_active_sop()
    ).generate(project(), artifact)

    non_factor_findings = [
        item
        for module in analysis.modules
        if module.module_id != "drivers_constraints"
        for item in module.findings
    ]
    assert non_factor_findings
    assert all(item.factor_role is None for item in non_factor_findings)
    assert all(item.impact_direction is None for item in non_factor_findings)


def test_null_comparison_dimensions_are_normalized_before_final_assembly() -> None:
    artifact, accepted_id, _ = evidence_artifact()
    generated = valid_payload(accepted_id)
    for module in generated["modules"]:
        if module["module_id"] not in {
            "market_value_chain",
            "competitive_landscape",
            "drivers_constraints",
        }:
            module["findings"][0]["comparison_dimensions"] = None

    analysis = IndustryAnalysisService(
        FakeModel(generated), load_active_sop()
    ).generate(project(), artifact)

    assert len(analysis.modules) == 5
    assert all(
        isinstance(item.comparison_dimensions, dict)
        for module in analysis.modules
        for item in module.findings
    )

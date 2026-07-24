"""Prompt-grounded report composition from human-approved artifacts."""

from __future__ import annotations

import json
from typing import Any, Protocol

from src.models.analysis import AnalysisReviewStatus
from src.models.evidence import EvidenceReviewStatus
from src.models.future import ForecastReviewStatus
from src.models.report import GeneralReportArtifact, PromptCoverageItem
from src.providers.base import ChatMessage, ModelResponse, ProviderError
from src.state.project import ProjectState


class ReportGenerationError(ValueError):
    pass


class StructuredModel(Protocol):
    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        enable_thinking: bool = False,
    ) -> tuple[dict[str, Any], ModelResponse]: ...


class ReportGenerationService:
    """Use the model for semantic coverage, never for ungrounded new facts."""

    def __init__(self, model: StructuredModel) -> None:
        self.model = model

    def generate(self, project: ProjectState) -> GeneralReportArtifact:
        questions = _must_answer_questions(project)
        coverage = self._assess_coverage(project, questions)
        return generate_general_report(project, coverage)

    def _assess_coverage(
        self,
        project: ProjectState,
        questions: list[str],
    ) -> list[PromptCoverageItem]:
        analysis = project.industry_analysis_artifact
        future = project.future_intelligence_artifact
        assert analysis is not None and future is not None
        findings = [
            {
                "finding_id": item.finding_id,
                "statement": item.statement,
                "evidence_ids": item.evidence_ids,
            }
            for item in analysis.findings
            if item.review_status == AnalysisReviewStatus.ACCEPTED
        ]
        trends = [
            {
                "trend_id": item.trend_id,
                "statement": item.forecast_statement,
                "evidence_ids": item.evidence_ids,
                "finding_ids": item.finding_ids,
            }
            for item in future.trends
            if item.review_status == ForecastReviewStatus.ACCEPTED
        ]
        contract = {
            "items": [
                {
                    "question_index": 0,
                    "coverage_status": "answered|partial|evidence_gap",
                    "evidence_ids": ["EVD-..."],
                    "finding_ids": ["FND-..."],
                    "trend_ids": ["TRD-..."],
                    "note": "why the approved material does or does not answer the question",
                }
            ]
        }
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是Research Coverage Auditor。只判断已人工批准的材料是否回答用户原始Prompt，"
                    "不得增加事实、数字、观点或常识。按语义比较，不按关键词匹配。每个问题必须输出"
                    "一次；证据不足必须标记evidence_gap。只输出合法JSON。"
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"用户原始Prompt：{project.research_objective}\n\n"
                    f"必答问题：{json.dumps(questions, ensure_ascii=False)}\n\n"
                    f"已批准行业判断：{json.dumps(findings, ensure_ascii=False)}\n\n"
                    f"已批准趋势：{json.dumps(trends, ensure_ascii=False)}\n\n"
                    f"严格输出结构：{json.dumps(contract, ensure_ascii=False)}"
                ),
            ),
        ]
        evidence_artifact = project.evidence_collection_artifact
        allowed_evidence = {
            item.evidence_id
            for item in evidence_artifact.evidence
            if item.review_status == EvidenceReviewStatus.ACCEPTED
        } if evidence_artifact else set()
        allowed_findings = {item["finding_id"] for item in findings}
        allowed_trends = {item["trend_id"] for item in trends}
        for attempt in range(2):
            response_content = "{}"
            try:
                payload, response = self.model.complete_json(messages, enable_thinking=True)
                response_content = response.content
                nested = payload.get("prompt_coverage")
                if isinstance(nested, dict):
                    payload = nested
                rows = payload.get("items")
                if not isinstance(rows, list) or len(rows) != len(questions):
                    raise ReportGenerationError("Prompt覆盖结果数量不完整")
                indices = {row.get("question_index") for row in rows if isinstance(row, dict)}
                if indices != set(range(len(questions))):
                    raise ReportGenerationError("Prompt覆盖结果未逐题对应")
                items: list[PromptCoverageItem] = []
                for row in sorted(rows, key=lambda item: item["question_index"]):
                    status = row.get("coverage_status")
                    if status not in {"answered", "partial", "evidence_gap"}:
                        raise ReportGenerationError("Prompt覆盖状态无效")
                    evidence_ids = list(row.get("evidence_ids") or [])
                    finding_ids = list(row.get("finding_ids") or [])
                    trend_ids = list(row.get("trend_ids") or [])
                    if not set(evidence_ids).issubset(allowed_evidence):
                        raise ReportGenerationError("Prompt覆盖引用了未批准Evidence ID")
                    if not set(finding_ids).issubset(allowed_findings):
                        raise ReportGenerationError("Prompt覆盖引用了未批准Finding ID")
                    if not set(trend_ids).issubset(allowed_trends):
                        raise ReportGenerationError("Prompt覆盖引用了未批准Trend ID")
                    items.append(
                        PromptCoverageItem(
                            question=questions[row["question_index"]],
                            coverage_status=status,
                            evidence_ids=evidence_ids,
                            finding_ids=finding_ids,
                            trend_ids=trend_ids,
                            note=str(row.get("note") or "未提供覆盖说明"),
                        )
                    )
                return items
            except (ProviderError, ReportGenerationError, TypeError, ValueError) as exc:
                if attempt == 1:
                    break
                messages.extend(
                    [
                        ChatMessage(role="assistant", content=response_content),
                        ChatMessage(
                            role="user",
                            content=f"覆盖校验失败：{exc}。逐题修复，不得添加未批准ID。",
                        ),
                    ]
                )
        return [
            PromptCoverageItem(
                question=question,
                coverage_status="evidence_gap",
                note="语义覆盖检查未能可靠完成；报告保留该问题作为待补充研究项。",
            )
            for question in questions
        ]


def _must_answer_questions(project: ProjectState) -> list[str]:
    brief = project.research_brief_artifact
    if brief is None:
        return [project.research_objective]
    return (
        brief.interpreted_intent.must_answer_questions
        or brief.key_questions
        or [project.research_objective]
    )


def generate_general_report(
    project: ProjectState,
    prompt_coverage: list[PromptCoverageItem] | None = None,
) -> GeneralReportArtifact:
    evidence = project.evidence_collection_artifact
    analysis = project.industry_analysis_artifact
    future = project.future_intelligence_artifact
    brief = project.research_brief_artifact
    if brief is None or not brief.human_confirmed:
        raise ReportGenerationError("Gate 0市场口径尚未确认")
    if evidence is None or not evidence.human_confirmed:
        raise ReportGenerationError("Gate 1证据真实性与可用性尚未确认")
    if analysis is None or not analysis.human_confirmed:
        raise ReportGenerationError("Gate 2行业分析内容尚未确认")
    if future is None or not future.human_confirmed:
        raise ReportGenerationError("Gate 2趋势与情景内容尚未确认")

    accepted_evidence = [
        item for item in evidence.evidence
        if item.review_status == EvidenceReviewStatus.ACCEPTED
    ]
    accepted_findings = [
        item for item in analysis.findings
        if item.review_status == AnalysisReviewStatus.ACCEPTED
    ]
    accepted_trends = [
        item for item in future.trends
        if item.review_status == ForecastReviewStatus.ACCEPTED
    ]
    accepted_scenarios = [
        item for item in future.scenarios
        if item.review_status == ForecastReviewStatus.ACCEPTED
    ]
    if not accepted_evidence or not accepted_findings or not accepted_trends:
        raise ReportGenerationError("报告缺少已确认的证据、行业判断或趋势")

    source_map = {source.source_id: source for source in evidence.sources}
    lines: list[str] = [
        f"# {project.project_name}",
        "",
        "> **报告状态：Human-reviewed General Industry Report**  ",
        "> 已完成市场口径对齐、证据真实性与可用性确认、报告内容确认。",
        "",
        f"- **行业：** {project.industry}",
        f"- **地区：** {project.region}",
        f"- **研究范围：** {project.time_horizon}",
        f"- **研究目标：** {project.research_objective}",
        "",
        "## 1. Executive Summary",
        "",
    ]
    for module in analysis.modules:
        if any(item.review_status == AnalysisReviewStatus.ACCEPTED for item in module.findings):
            lines.append(f"- **{module.title}：** {module.executive_summary}")
    coverage = prompt_coverage or []
    lines.extend(["", "## 2. Original Prompt Coverage", ""])
    if coverage:
        for item in coverage:
            references = [*item.evidence_ids, *item.finding_ids, *item.trend_ids]
            reference_text = "、".join(references) if references else "暂无可引用的已批准材料"
            lines.extend(
                [
                    f"### {item.question}",
                    "",
                    f"- **覆盖状态：** {item.coverage_status}",
                    f"- **覆盖说明：** {item.note}",
                    f"- **追溯ID：** {reference_text}",
                    "",
                ]
            )
    else:
        lines.append("- 尚未运行Prompt语义覆盖检查。")
    lines.extend(["", "## 3. Research Question & Market Definition", ""])
    if brief:
        market = brief.market_definition
        lines.extend(
            [
                brief.decision_statement,
                "",
                f"- 核心市场：{market.core_market}",
                f"- 产品/服务范围：{market.product_scope}",
                f"- 客户范围：{market.customer_scope}",
                f"- 地域范围：{market.geography_scope}",
                f"- 价值链范围：{market.value_chain_scope}",
                f"- 包含项：{'；'.join(market.inclusions)}",
                f"- 排除项：{'；'.join(market.exclusions)}",
            ]
        )
    else:
        lines.append(project.research_objective)

    section_number = 4
    for module in analysis.modules:
        module_findings = [
            item for item in module.findings
            if item.review_status == AnalysisReviewStatus.ACCEPTED
        ]
        if not module_findings:
            continue
        lines.extend(["", f"## {section_number}. {module.title}", "", module.executive_summary, ""])
        for item in module_findings:
            evidence_refs = ", ".join(f"`{item_id}`" for item_id in item.evidence_ids)
            lines.extend(
                [
                    f"### {item.subject}",
                    "",
                    item.statement,
                    "",
                    f"- **机制：** {item.mechanism}",
                    f"- **证据：** {evidence_refs}",
                    f"- **置信度：** {item.confidence:.0%}",
                    f"- **不确定性：** {item.uncertainty}",
                    f"- **边界/反证条件：** {item.boundary_condition}",
                    "",
                ]
            )
        if module.evidence_gaps:
            lines.append("**本模块证据缺口：** " + "；".join(module.evidence_gaps))
        section_number += 1

    company_findings = [
        item for item in analysis.company_implications
        if item.review_status == AnalysisReviewStatus.ACCEPTED
    ]
    if company_findings:
        lines.extend(["", f"## {section_number}. Target Company Exposure (Not a Scorecard)", ""])
        for item in company_findings:
            lines.extend(
                [
                    f"### {item.subject}",
                    "",
                    item.statement,
                    "",
                    f"- **机制：** {item.mechanism}",
                    f"- **不确定性：** {item.uncertainty}",
                    f"- **边界条件：** {item.boundary_condition}",
                    "",
                ]
            )
        section_number += 1

    lines.extend(["", f"## {section_number}. Future Intelligence", ""])
    for trend in accepted_trends:
        lines.extend(
            [
                f"### {trend.title}",
                "",
                trend.forecast_statement,
                "",
                f"- **预测范围：** {trend.forecast_horizon}",
                f"- **因果机制：** {'；'.join(trend.causal_mechanism)}",
                f"- **竞争影响：** {trend.competition_impact}",
                f"- **商业模式影响：** {trend.business_model_impact}",
                f"- **客户需求影响：** {trend.customer_demand_impact}",
                f"- **系统置信度：** {trend.confidence.overall}/100",
                f"- **可证伪条件：** {'；'.join(trend.falsification_conditions)}",
                "",
            ]
        )
    lines.extend(["### Scenarios", ""])
    for scenario in accepted_scenarios:
        lines.extend(
            [
                f"- **{scenario.title}（{scenario.likelihood_label}）：** {scenario.narrative}",
                f"  - 触发条件：{'；'.join(scenario.trigger_conditions)}",
                f"  - 预期结果：{'；'.join(scenario.expected_outcomes)}",
            ]
        )
    section_number += 1

    lines.extend(["", f"## {section_number}. Risks, Counter-evidence & Limitations", ""])
    limitations = [
        *analysis.cross_module_conflicts,
        *analysis.overall_evidence_limitations,
        *future.forecast_gaps,
    ]
    if limitations:
        lines.extend(f"- {item}" for item in limitations)
    else:
        lines.append("- 当前未记录额外限制；仍需持续监测来源更新和反证信号。")
    section_number += 1

    lines.extend(["", f"## {section_number}. Evidence Matrix", ""])
    for item in accepted_evidence:
        source = source_map[item.source_id]
        lines.extend(
            [
                f"### {item.evidence_id} · {item.kind.value}",
                "",
                item.statement,
                "",
                f"> {item.supporting_excerpt}",
                "",
                f"来源：[{source.title}]({source.url}) · 等级 {source.source_tier.value} · QA {item.qa_score}/100",
                "",
            ]
        )
    section_number += 1
    lines.extend(
        [
            "",
            f"## {section_number}. Human Review Record",
            "",
            "- Gate 0：用户已确认AI对原始Prompt和市场口径的理解。",
            "- Gate 1：用户已确认报告采用证据的真实性与研究可用性。",
            "- Gate 2：用户已确认进入报告的行业判断、趋势和情景内容。",
            "- 报告不包含Company Scorecard或Action Plan；企业战略建议需要额外企业输入。",
        ]
    )

    unique_sources = {source_map[item.source_id].url for item in accepted_evidence}
    return GeneralReportArtifact(
        title=project.project_name,
        markdown="\n".join(lines).strip() + "\n",
        accepted_evidence_ids=[item.evidence_id for item in accepted_evidence],
        accepted_finding_ids=[item.finding_id for item in accepted_findings],
        accepted_trend_ids=[item.trend_id for item in accepted_trends],
        accepted_scenario_ids=[item.scenario_id for item in accepted_scenarios],
        prompt_coverage=coverage,
        unresolved_prompt_questions=[
            item.question for item in coverage
            if item.coverage_status != "answered"
        ],
        source_count=len(unique_sources),
    )

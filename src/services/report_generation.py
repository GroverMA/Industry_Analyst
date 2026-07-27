"""Prompt-grounded report composition from human-approved artifacts."""

from __future__ import annotations

import json
import re
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
        narrative = self._compose_narrative(project, coverage)
        return generate_general_report(project, coverage, narrative)

    def _compose_narrative(
        self,
        project: ProjectState,
        coverage: list[PromptCoverageItem],
    ) -> dict[str, Any] | None:
        """Ask the model to edit approved material into formal analyst prose.

        This is a language-editing stage, not a new research stage.  Every
        paragraph is keyed to an already approved artifact so a malformed or
        ungrounded response can be discarded without blocking report delivery.
        """

        analysis = project.industry_analysis_artifact
        future = project.future_intelligence_artifact
        brief = project.research_brief_artifact
        assert analysis is not None and future is not None and brief is not None
        modules = []
        findings = []
        for module in analysis.modules:
            accepted = [
                item
                for item in module.findings
                if item.review_status == AnalysisReviewStatus.ACCEPTED
            ]
            if not accepted:
                continue
            modules.append(
                {
                    "module_id": module.module_id,
                    "title": module.title,
                    "executive_summary": module.executive_summary,
                }
            )
            findings.extend(
                {
                    "finding_id": item.finding_id,
                    "subject": item.subject,
                    "statement": item.statement,
                    "mechanism": item.mechanism,
                    "evidence_ids": item.evidence_ids,
                    "counter_evidence_ids": item.counter_evidence_ids,
                    "confidence": item.confidence,
                    "uncertainty": item.uncertainty,
                    "boundary_condition": item.boundary_condition,
                }
                for item in accepted
            )
        trends = [
            {
                "trend_id": item.trend_id,
                "title": item.title,
                "forecast_statement": item.forecast_statement,
                "forecast_horizon": item.forecast_horizon,
                "causal_mechanism": item.causal_mechanism,
                "competition_impact": item.competition_impact,
                "business_model_impact": item.business_model_impact,
                "customer_demand_impact": item.customer_demand_impact,
                "falsification_conditions": item.falsification_conditions,
                "uncertainties": item.uncertainties,
                "confidence": item.confidence.overall,
                "evidence_ids": item.evidence_ids,
                "finding_ids": item.finding_ids,
            }
            for item in future.trends
            if item.review_status == ForecastReviewStatus.ACCEPTED
        ]
        scenarios = [
            {
                "scenario_id": item.scenario_id,
                "title": item.title,
                "likelihood_label": item.likelihood_label,
                "narrative": item.narrative,
                "trigger_conditions": item.trigger_conditions,
                "expected_outcomes": item.expected_outcomes,
                "falsification_conditions": item.falsification_conditions,
            }
            for item in future.scenarios
            if item.review_status == ForecastReviewStatus.ACCEPTED
        ]
        contract = {
            "executive_summary": "完整正式段落",
            "prompt_responses": [
                {"question_index": 0, "paragraph": "直接回应该问题的正式段落"}
            ],
            "module_introductions": [
                {"module_id": "market_status", "paragraph": "该章节的判断性导语"}
            ],
            "finding_paragraphs": [
                {"finding_id": "FND-...", "paragraph": "事实、机制、影响与边界组成的完整段落"}
            ],
            "trend_paragraphs": [
                {"trend_id": "TRD-...", "paragraph": "区分事实与预测的完整段落"}
            ],
            "scenario_paragraphs": [
                {"scenario_id": "SCN-...", "paragraph": "触发条件与结果组成的完整段落"}
            ],
            "limitations_paragraph": "证据限制、反证条件与适用边界组成的完整段落",
        }
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是港股招股书及沙利文行业报告的高级文字编辑。仅可重组和改写已人工批准的材料，"
                    "不得新增事实、数字、公司、来源、因果关系或确定性。写作采用正式、客观、审慎的"
                    "机构研究语体：章节标题下使用完整连续段落；先陈述现象或判断，再解释作用机制、"
                    "市场影响及适用边界；预测必须使用‘预计’‘可能’‘在……条件下’等审慎表达，并"
                    "明确反证条件。不得使用emoji、箭头、项目符号、口语、AI自述、营销口号、Markdown"
                    "标题或表格。不得把相关性写成因果。仅输出合法JSON。"
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"原始研究Prompt：{project.research_objective}\n\n"
                    f"市场口径：{brief.market_definition.model_dump_json()}\n\n"
                    f"Prompt覆盖：{json.dumps([item.model_dump(mode='json') for item in coverage], ensure_ascii=False)}\n\n"
                    f"章节：{json.dumps(modules, ensure_ascii=False)}\n\n"
                    f"已批准判断：{json.dumps(findings, ensure_ascii=False)}\n\n"
                    f"已批准趋势：{json.dumps(trends, ensure_ascii=False)}\n\n"
                    f"已批准情景：{json.dumps(scenarios, ensure_ascii=False)}\n\n"
                    f"严格输出结构：{json.dumps(contract, ensure_ascii=False)}"
                ),
            ),
        ]
        try:
            payload, _ = self.model.complete_json(messages, enable_thinking=True)
            nested = payload.get("report_narrative")
            if isinstance(nested, dict):
                payload = nested
            _validate_narrative_payload(
                payload,
                question_count=len(coverage),
                module_ids={item["module_id"] for item in modules},
                finding_ids={item["finding_id"] for item in findings},
                trend_ids={item["trend_id"] for item in trends},
                scenario_ids={item["scenario_id"] for item in scenarios},
            )
            return payload
        except (ProviderError, ReportGenerationError, TypeError, ValueError):
            return None

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


def _generate_structured_audit_report_legacy(
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


_REPORT_SYMBOLS = re.compile(
    "[\u2190-\u21ff\u2600-\u27bf\U0001F000-\U0001FAFF]"
)


def _plain_report_prose(value: Any) -> str:
    """Normalize model or artifact text into restrained institutional prose."""

    text = str(value or "").strip()
    text = _REPORT_SYMBOLS.sub("", text)
    text = re.sub(r"(?m)^\s*(?:[-*•]+|\d+[.)])\s+", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sentence(value: Any) -> str:
    text = _plain_report_prose(value)
    if text and text[-1] not in "。！？；.!?;":
        text += "。"
    return text


def _formal_paragraph(*parts: Any) -> str:
    return "".join(_sentence(part) for part in parts if _plain_report_prose(part))


def _validate_narrative_payload(
    payload: Any,
    *,
    question_count: int,
    module_ids: set[str],
    finding_ids: set[str],
    trend_ids: set[str],
    scenario_ids: set[str],
) -> None:
    if not isinstance(payload, dict) or not _plain_report_prose(payload.get("executive_summary")):
        raise ReportGenerationError("正式报告叙事缺少执行摘要")

    def validate_rows(key: str, identity: str, expected: set[Any]) -> None:
        rows = payload.get(key)
        if not isinstance(rows, list):
            raise ReportGenerationError(f"正式报告叙事缺少{key}")
        received = {
            row.get(identity)
            for row in rows
            if isinstance(row, dict) and _plain_report_prose(row.get("paragraph"))
        }
        if received != expected:
            raise ReportGenerationError(f"正式报告叙事的{key}与批准材料不一致")

    validate_rows("prompt_responses", "question_index", set(range(question_count)))
    validate_rows("module_introductions", "module_id", module_ids)
    validate_rows("finding_paragraphs", "finding_id", finding_ids)
    validate_rows("trend_paragraphs", "trend_id", trend_ids)
    validate_rows("scenario_paragraphs", "scenario_id", scenario_ids)
    if not _plain_report_prose(payload.get("limitations_paragraph")):
        raise ReportGenerationError("正式报告叙事缺少证据边界")


def _narrative_map(
    narrative: dict[str, Any] | None,
    key: str,
    identity: str,
) -> dict[Any, str]:
    if not narrative:
        return {}
    rows = narrative.get(key)
    if not isinstance(rows, list):
        return {}
    return {
        row.get(identity): _plain_report_prose(row.get("paragraph"))
        for row in rows
        if isinstance(row, dict) and _plain_report_prose(row.get("paragraph"))
    }


def generate_general_report(
    project: ProjectState,
    prompt_coverage: list[PromptCoverageItem] | None = None,
    narrative: dict[str, Any] | None = None,
) -> GeneralReportArtifact:
    """Compose a formal, evidence-bound industry report in complete paragraphs."""

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
    coverage = prompt_coverage or []
    prompt_paragraphs = _narrative_map(
        narrative, "prompt_responses", "question_index"
    )
    module_paragraphs = _narrative_map(
        narrative, "module_introductions", "module_id"
    )
    finding_paragraphs = _narrative_map(
        narrative, "finding_paragraphs", "finding_id"
    )
    trend_paragraphs = _narrative_map(
        narrative, "trend_paragraphs", "trend_id"
    )
    scenario_paragraphs = _narrative_map(
        narrative, "scenario_paragraphs", "scenario_id"
    )

    status_paragraph = (
        "本报告依据经人工确认的市场口径、公开证据、行业判断及趋势情景形成，"
        "报告结论均受所列研究范围、证据时点及反证条件约束。"
    )
    scope_paragraph = _formal_paragraph(
        f"本报告研究对象为{project.region}的{project.industry}行业，研究时间范围为{project.time_horizon}",
        f"核心研究目标为{project.research_objective}",
    )
    lines: list[str] = [
        f"# {project.project_name}",
        "",
        status_paragraph,
        "",
        scope_paragraph,
        "",
        "## 1. 执行摘要",
        "",
    ]
    executive_summary = _plain_report_prose(
        narrative.get("executive_summary") if narrative else ""
    )
    if executive_summary:
        lines.append(executive_summary)
    else:
        lines.append(
            _formal_paragraph(
                *[
                    module.executive_summary
                    for module in analysis.modules
                    if any(
                        item.review_status == AnalysisReviewStatus.ACCEPTED
                        for item in module.findings
                    )
                ]
            )
        )

    lines.extend(["", "## 2. 对原始研究问题的回应", ""])
    if coverage:
        status_labels = {
            "answered": "现有证据已形成直接回应",
            "partial": "现有证据仅形成部分回应",
            "evidence_gap": "现有证据尚不足以形成确定回应",
        }
        for index, item in enumerate(coverage):
            references = "、".join(
                [*item.evidence_ids, *item.finding_ids, *item.trend_ids]
            ) or "尚无可采用的已批准材料"
            fallback = _formal_paragraph(
                status_labels.get(item.coverage_status, "现有材料需要进一步核验"),
                item.note,
                f"相关追溯记录为{references}",
            )
            lines.extend(
                [
                    f"### 2.{index + 1} {item.question}",
                    "",
                    prompt_paragraphs.get(index) or fallback,
                    "",
                ]
            )
    else:
        lines.append("现有流程尚未形成原始研究问题的语义覆盖记录，相关问题应作为后续补充研究事项。")

    market = brief.market_definition
    market_paragraph = _formal_paragraph(
        brief.decision_statement,
        (
            f"本次研究所称核心市场为{market.core_market}，产品及服务范围为{market.product_scope}，"
            f"客户范围为{market.customer_scope}，地域范围为{market.geography_scope}，"
            f"并覆盖{market.value_chain_scope}"
        ),
        f"纳入范围包括{'、'.join(market.inclusions)}" if market.inclusions else "",
        f"排除范围包括{'、'.join(market.exclusions)}" if market.exclusions else "",
    )
    lines.extend(["", "## 3. 研究范围与市场定义", "", market_paragraph])

    section_number = 4
    for module in analysis.modules:
        module_findings = [
            item for item in module.findings
            if item.review_status == AnalysisReviewStatus.ACCEPTED
        ]
        if not module_findings:
            continue
        lines.extend(
            [
                "",
                f"## {section_number}. {module.title}",
                "",
                module_paragraphs.get(module.module_id)
                or _plain_report_prose(module.executive_summary),
                "",
            ]
        )
        for item_index, item in enumerate(module_findings, start=1):
            references = "、".join(item.evidence_ids)
            counter = (
                f"反向证据记录为{'、'.join(item.counter_evidence_ids)}"
                if item.counter_evidence_ids
                else ""
            )
            fallback = _formal_paragraph(
                item.statement,
                item.mechanism,
                f"该判断置信度为{item.confidence:.0%}，其主要不确定性为{item.uncertainty}",
                f"该判断在{item.boundary_condition}的情形下需要重新评估",
                counter,
                f"相关证据记录为{references}",
            )
            lines.extend(
                [
                    f"### {section_number}.{item_index} {item.subject}",
                    "",
                    finding_paragraphs.get(item.finding_id) or fallback,
                    "",
                ]
            )
        if module.evidence_gaps:
            lines.append(
                _formal_paragraph(
                    "本章节仍存在证据限制",
                    "；".join(module.evidence_gaps),
                )
            )
        section_number += 1

    lines.extend(["", f"## {section_number}. 未来发展趋势与情景", ""])
    for trend_index, trend in enumerate(accepted_trends, start=1):
        fallback = _formal_paragraph(
            trend.forecast_statement,
            f"该预测适用于{trend.forecast_horizon}，主要作用机制包括{'、'.join(trend.causal_mechanism)}",
            f"其对竞争格局的潜在影响为{trend.competition_impact}",
            f"其对商业模式的潜在影响为{trend.business_model_impact}",
            f"其对客户需求的潜在影响为{trend.customer_demand_impact}",
            f"系统置信度为{trend.confidence.overall}分",
            f"若出现{'、'.join(trend.falsification_conditions)}，则应重新评估该预测",
        )
        lines.extend(
            [
                f"### {section_number}.{trend_index} {trend.title}",
                "",
                trend_paragraphs.get(trend.trend_id) or fallback,
                "",
            ]
        )

    lines.extend([f"### {section_number}.{len(accepted_trends) + 1} 情景分析", ""])
    for scenario in accepted_scenarios:
        fallback = _formal_paragraph(
            scenario.narrative,
            f"该情景的当前可能性判断为{scenario.likelihood_label}",
            f"其触发条件包括{'、'.join(scenario.trigger_conditions)}",
            f"若相关条件成立，预期结果包括{'、'.join(scenario.expected_outcomes)}",
            f"若出现{'、'.join(scenario.falsification_conditions)}，则该情景需要调整或失效",
        )
        lines.extend(
            [
                f"#### {scenario.title}",
                "",
                scenario_paragraphs.get(scenario.scenario_id) or fallback,
                "",
            ]
        )
    section_number += 1

    limitations = [
        *analysis.cross_module_conflicts,
        *analysis.overall_evidence_limitations,
        *future.forecast_gaps,
    ]
    limitations_paragraph = _plain_report_prose(
        narrative.get("limitations_paragraph") if narrative else ""
    ) or _formal_paragraph(
        "本报告结论应结合证据时点、来源覆盖和市场口径审慎使用",
        "；".join(limitations)
        if limitations
        else "当前未记录额外证据冲突，但仍需持续监测来源更新及反证信号",
    )
    lines.extend(
        [
            "",
            f"## {section_number}. 证据边界、反证条件及研究限制",
            "",
            limitations_paragraph,
        ]
    )
    section_number += 1

    lines.extend(["", f"## {section_number}. 附录：证据索引", ""])
    for item in accepted_evidence:
        source = source_map[item.source_id]
        evidence_paragraph = _formal_paragraph(
            item.statement,
            f"原始材料摘录为“{_plain_report_prose(item.supporting_excerpt)}”",
            f"该证据质量评分为{item.qa_score}分，来源等级为{source.source_tier.value}",
        )
        lines.extend(
            [
                f"### {item.evidence_id} · {item.kind.value}",
                "",
                evidence_paragraph,
                "",
                f"来源：[{{}}]({{}})".format(source.title, source.url),
                "",
            ]
        )
    section_number += 1
    lines.extend(
        [
            "",
            f"## {section_number}. 人工审核及责任边界",
            "",
            (
                "本报告已经完成市场口径确认、证据真实性与研究可用性确认，以及拟纳入报告的行业判断、"
                "趋势与情景确认。通用行业研究报告不包含公司能力评分或企业行动计划；如需形成企业"
                "战略建议，仍须补充目标企业战略意图及经确认的一手企业资料，并由相应责任主体完成最终判断。"
            ),
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

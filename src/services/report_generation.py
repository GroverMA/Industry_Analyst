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
            "section_plan": [
                {"section_key": "industry_definition", "title": "按原始Prompt调整后的章节标题"},
                {"section_key": "market_value_chain", "title": "按原始Prompt调整后的章节标题"},
                {"section_key": "market_status", "title": "按原始Prompt调整后的章节标题"},
                {"section_key": "competitive_landscape", "title": "按原始Prompt调整后的章节标题"},
                {"section_key": "drivers_constraints", "title": "按原始Prompt调整后的章节标题"},
                {"section_key": "future_outlook", "title": "按原始Prompt调整后的章节标题"},
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
        }
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是港股招股书及沙利文行业报告的高级文字编辑。仅可重组和改写已人工批准的材料，"
                    "不得新增事实、数字、公司、来源、因果关系或确定性。写作采用正式、客观、审慎的"
                    "机构研究语体：章节标题下使用完整连续段落；先陈述现象或判断，再解释作用机制、"
                    "市场影响及适用边界；预测必须使用‘预计’‘可能’‘在……条件下’等审慎表达，并"
                    "明确反证条件。原始Prompt只用于确定研究重点和篇幅，不得按问答形式逐题回应。"
                    "报告必须依次覆盖行业定义、行业赛道与产业链、市场或特定赛道规模测算、"
                    "竞争格局、市场驱动因素及Future Outlook六个部分。章节顺序不得改变；章节标题"
                    "应按用户原始Prompt动态命名，Prompt最关注的部分应增加信息密度与篇幅，但不得"
                    "改写为逐题问答。市场规模必须给出基于现有数据交叉推算的中心估计或合理区间，"
                    "并说明主测算公式、数量端输入、价格或单位价值输入、分项加总、重叠剔除及独立"
                    "验证方法。"
                    "不得写无法量化或缺乏数据；不得机械套用单一CAGR；"
                    "驱动及趋势必须保持事实、机制、直接变量、行业影响与验证指标的闭环。"
                    "正文采用独立第三方视角直接表达结论，不得出现‘根据券商/研报/已接受证据’、"
                    "‘本模块只能覆盖’、‘证据不足/证据缺口/无法量化’、‘建议补充来源’等过程性"
                    "措辞。证据、置信度和审阅提醒只属于内部底稿，不得写入正式报告正文。"
                    "不得输出任何EVD、FND、TRD、SCN、SRC等内部编码，也不得使用emoji、箭头、项目"
                    "符号、口语、AI自述、营销口号、Markdown标题或表格。不得把相关性写成因果。"
                    "仅输出合法JSON。"
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
            # The governed narrative contract already contains the full research
            # logic.  Disabling exposed chain-of-thought reduces latency and keeps
            # report delivery recoverable through the deterministic compositor.
            payload, _ = self.model.complete_json(messages, enable_thinking=False)
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
                payload, response = self.model.complete_json(messages, enable_thinking=False)
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
                if isinstance(exc, ProviderError) and "timed out" in str(exc).lower():
                    break
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
                coverage_status="partial",
                note=(
                    "当前材料已进入报告草稿；请Reviewer在Content Revision中重点核对该研究重点的"
                    "结论强度与表述范围。"
                ),
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
    for scenario_index, scenario in enumerate(accepted_scenarios, start=1):
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
                f"来源：[{source.title}]({source.url}) · 质量评分 {item.qa_score}/100",
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
_INTERNAL_REFERENCE_CODE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:EVD|FND|TRD|SCN|SRC|ENT|DIM|ACT)"
    r"\s*[-–—_]\s*[A-Za-z0-9_-]+"
)


def _normalize_chinese_typography(value: Any) -> str:
    """Repair common model spacing and punctuation artefacts in Chinese prose."""

    text = str(value or "")
    text = text.replace("`", "").replace("´", "").replace("•", "")
    replacements = {
        "capacity": "产能",
        "pricing": "定价",
        "penetration": "渗透率",
        "margin": "盈利能力",
        "volume": "需求量",
    }
    for source, target in replacements.items():
        text = re.sub(rf"\b{source}\b", target, text, flags=re.IGNORECASE)
    text = re.sub(r"[\u00a0\u2000-\u200b\u202f\u205f\u3000]+", " ", text)
    text = re.sub(r"\s+([，。；：！？、）》】])", r"\1", text)
    text = re.sub(r"([（《【])\s+", r"\1", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[A-Z]{2,}[0-9A-Z-]*\b)", "", text)
    text = re.sub(r"(?<=[A-Z0-9%])\s+(?=[\u3400-\u9fff])", "", text)
    text = re.sub(r"([，。；：！？、]){2,}", lambda match: match.group(0)[-1], text)
    text = re.sub(r"^[\s、，；;:：]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _plain_report_prose(value: Any) -> str:
    """Normalize model or artifact text into restrained institutional prose."""

    text = str(value or "").strip()
    text = _INTERNAL_REFERENCE_CODE.sub("", text)
    text = _REPORT_SYMBOLS.sub("", text)
    text = re.sub(r"(?m)^\s*(?:[-*•]+|\d+[.)])\s+", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)
    text = re.sub(r"\s*#{1,6}\s+", " ", text)
    text = re.sub(r"(?:该|相关)?(?:报告|文章|资料)(预计|估计|认为|强调|显示|指出)", r"\1", text)
    text = re.sub(r"根据(?:券商|研究报告|研报)(?:的)?(?:预测|判断|数据)?[，,:：]?", "", text)
    text = text.replace("volume", "需求量").replace("price", "价格")
    text = text.replace("cost", "成本").replace("penetration", "渗透率")
    text = text.replace("margin", "盈利能力").replace("capacity", "产能")
    text = text.replace("pricing", "定价").replace("demand", "需求").replace("supply", "供给")
    text = re.sub(r"\bmixed\b", "双向", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmoderate\b", "中等", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpositive\b", "正向", text, flags=re.IGNORECASE)
    text = re.sub(r"\bnegative\b", "负向", text, flags=re.IGNORECASE)
    text = re.sub(r"\blow\b", "较低", text, flags=re.IGNORECASE)
    text = re.sub(r"\bhigh\b", "较高", text, flags=re.IGNORECASE)
    text = re.sub(r"若出现若", "若出现", text)
    return _normalize_chinese_typography(text)


def _scenario_title(value: Any) -> str:
    """Return a reader-facing Chinese scenario name without internal enum labels."""

    text = _plain_report_prose(value)
    labels = {
        "baseline": "基准情景",
        "base case": "基准情景",
        "accelerated": "加速情景",
        "upside": "上行情景",
        "blocked": "受阻情景",
        "downside": "下行情景",
    }
    return labels.get(text.lower(), text)


def _markdown_link(label: Any, url: Any) -> str:
    """Build a source link that survives spaces, brackets and parentheses."""

    safe_label = str(label or "资料来源").replace("[", "［").replace("]", "］")
    safe_url = (
        str(url or "").strip()
        .replace(" ", "%20")
        .replace("(", "%28")
        .replace(")", "%29")
    )
    return f"[{safe_label}]({safe_url})"


def _sentence(value: Any) -> str:
    text = _plain_report_prose(value)
    if text and text[-1] not in "。！？；.!?;":
        text += "。"
    return text


def _formal_paragraph(*parts: Any) -> str:
    return "".join(_sentence(part) for part in parts if _plain_report_prose(part))


def _paragraph_blocks(value: Any, *, max_chars: int = 420) -> list[str]:
    """Create readable logic-complete paragraphs without arbitrary line breaks."""

    text = _plain_report_prose(value)
    if not text:
        return []
    protected_links: list[str] = []

    def protect_link(match: re.Match[str]) -> str:
        protected_links.append(match.group(0))
        return f"〔引用链接{len(protected_links) - 1}〕"

    text = re.sub(r"\[[^\]]+\]\(https?://[^)]+\)", protect_link, text)
    sentences = [
        item.strip()
        for item in re.findall(r".*?(?:[。！？；.!?;]|$)", text)
        if item.strip()
    ]
    blocks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            blocks.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        blocks.append(current)
    if len(blocks) > 1 and len(blocks[-1]) < 90 and len(blocks[-2]) + len(blocks[-1]) <= max_chars + 80:
        tail = blocks.pop()
        blocks[-1] += tail
    for index, link in enumerate(protected_links):
        blocks = [block.replace(f"〔引用链接{index}〕", link) for block in blocks]
    return blocks


def _append_paragraphs(lines: list[str], value: Any) -> None:
    for block in _paragraph_blocks(value):
        lines.extend([block, ""])


_INTERNAL_REPORT_SENTENCES = re.compile(
    r"[^\n。！？.!?]*(?:证据不足|证据缺口|证据限制|无(?:直接)?证据支持|"
    r"缺乏(?:直接)?数据|无法量化|无法测算|"
    r"本模块(?:仅能|只能)|基于已(?:接受|批准|确认)证据|根据(?:券商|研报|研究报告)|"
    r"建议补充(?:官方数据|企业披露|专家访谈|来源)|evidence_gaps|Evidence ID|"
    r"结构修复|Reviewer(?:修改|审阅)?环节|本轮行业判断)[^\n。！？.!?]*[。！？.!?]?",
    re.IGNORECASE,
)

_FORMAL_REPORT_INTERNAL_MARKERS = re.compile(
    r"(?:Research Brief|Evidence(?: ID)?|Finding ID|Trend ID|"
    r"证据|证据链|来源等级|来源方|公开分类数据|"
    r"(?:券商|研报|研究报告)(?:预测|推算|数据|口径)?|"
    r"Tier\s*[0-9ABC]|置信度|缺乏|缺少|无法|未纳入|暂不评估|"
    r"无公开|未形成|待补充|建议补充|本模块|Reviewer|结构修复|"
    r"直接提供(?:具体)?(?:预测)?数字|提供(?:了)?(?:半年度|高频|具体)?参照|"
    r"(?:研究院|公告|机构|平台|媒体|协会).{0,28}(?:提供|给出|指出|显示|发布)|"
    r"支持(?:上游|中游|下游|本轮|该)?(?:高利润|利润|判断|推断|结论))",
    re.IGNORECASE,
)


def _scrub_formal_paragraph(line: str) -> str:
    """Keep conclusions while removing source/process and uncertainty narration."""

    text = _INTERNAL_REFERENCE_CODE.sub("", line)
    protected_links: list[str] = []

    def protect_link(match: re.Match[str]) -> str:
        protected_links.append(match.group(0))
        return f"〔链接{len(protected_links) - 1}〕"

    text = re.sub(r"\[[^\]]+\]\(https?://[^)]+\)", protect_link, text)
    text = re.sub(
        r"基于已确认的?Research Brief和(?:所)?提供的公开证据[，,:：]?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"基于(?:现有)?公开资料(?:的)?", "", text)
    text = re.sub(r"\s*[（(]\s*[）)]", "", text)
    sentences = [
        item.strip()
        for item in re.findall(r".*?(?:[。！？.!?]|$)", text)
        if item.strip()
    ]
    kept = [item for item in sentences if not _FORMAL_REPORT_INTERNAL_MARKERS.search(item)]
    cleaned = "".join(kept)
    cleaned = re.sub(r"\s*[（(]\s*[）)]", "", cleaned)
    cleaned = re.sub(r"[，,]\s*[，,]", "，", cleaned)
    cleaned = re.sub(r"若出现若", "若出现", cleaned)
    for index, link in enumerate(protected_links):
        cleaned = cleaned.replace(f"〔链接{index}〕", link)
    return _normalize_chinese_typography(cleaned)


def _strip_heading_number(title: str) -> str:
    return re.sub(
        r"^(?:\d+(?:[.．]\d+){0,3}|[A-Z](?:[.．]\d+)*)"
        r"(?:[.．、:]|\s+|(?=[\u3400-\u9fff]))",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()


def _normalize_formal_heading_hierarchy(markdown: str) -> str:
    """Renumber every generated or Reviewer-edited report in reading order."""

    top_level = 0
    second_level = 0
    third_level = 0
    normalized: list[str] = []
    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if not heading:
            normalized.append(line)
            continue
        marks, raw_title = heading.groups()
        level = len(marks)
        title = _strip_heading_number(raw_title)
        if level == 1:
            normalized.append(f"# {title}")
            continue
        if level == 2 and (title.startswith("执行摘要") or title.startswith("附录")):
            normalized.append(f"## {title}")
            continue
        if level == 2:
            top_level += 1
            second_level = 0
            third_level = 0
            normalized.append(f"## {top_level}. {title}")
            continue
        if level == 3:
            second_level += 1
            third_level = 0
            normalized.append(f"### {top_level}.{second_level} {title}")
            continue
        third_level += 1
        normalized.append(f"#### {top_level}.{second_level}.{third_level} {title}")
    return "\n".join(normalized)


def sanitize_formal_report(markdown: str) -> str:
    """Remove internal workflow language from a client-facing report.

    Traceability is preserved in artifact metadata and Reviewer workpapers;
    formal prose remains an independent third-party research deliverable.
    """

    text = _INTERNAL_REFERENCE_CODE.sub("", markdown)
    text = _INTERNAL_REPORT_SENTENCES.sub("", text)
    text = re.sub(r"(?m)^## 附录A：证据边界、反证条件及研究限制\s*$.*?(?=^## |\Z)", "", text, flags=re.S)
    text = re.sub(r"(?m)^## 附录C：研究说明\s*$.*?(?=^## |\Z)", "", text, flags=re.S)
    cleaned_lines: list[str] = []
    in_references = False
    for line in text.splitlines():
        if line.startswith("## 附录：资料来源"):
            in_references = True
            cleaned_lines.append(line)
            continue
        if in_references:
            cleaned_lines.append(_INTERNAL_REFERENCE_CODE.sub("", line).replace("`", ""))
            continue
        if line.startswith("#"):
            heading = re.match(r"^(#{1,6})\s+(.*)$", line)
            if heading:
                title = _normalize_chinese_typography(_INTERNAL_REFERENCE_CODE.sub("", heading.group(2)))
                cleaned_lines.append(f"{heading.group(1)} {title}")
            continue
        if not line.strip():
            cleaned_lines.append(line)
            continue
        if line.lstrip().startswith("|"):
            cleaned_lines.append(_normalize_chinese_typography(_INTERNAL_REFERENCE_CODE.sub("", line)))
            continue
        cleaned = _scrub_formal_paragraph(line)
        if cleaned:
            cleaned_lines.append(cleaned)
    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _normalize_formal_heading_hierarchy(text)
    text = _INTERNAL_REFERENCE_CODE.sub("", text)
    return text.strip() + "\n"


def _report_section_plan(project: ProjectState, narrative: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Keep the SOP sequence fixed while letting the Prompt shape chapter names."""

    defaults = {
        "industry_definition": "行业定义与研究边界",
        "market_value_chain": "行业赛道与产业链",
        "market_status": "市场规模、结构与发展现状",
        "competitive_landscape": "竞争格局与主要市场参与者",
        "drivers_constraints": "市场驱动因素与关键条件",
        "future_outlook": "未来发展趋势与Future Outlook",
    }
    allowed = set(defaults)
    proposed = narrative.get("section_plan") if narrative else None
    proposed_titles: dict[str, str] = {}
    if isinstance(proposed, list):
        for row in proposed:
            if not isinstance(row, dict):
                continue
            key = str(row.get("section_key") or "")
            title = _plain_report_prose(row.get("title"))
            if key == "drivers_future":
                proposed_titles.setdefault("drivers_constraints", "市场驱动因素与关键条件")
                proposed_titles.setdefault("future_outlook", title or defaults["future_outlook"])
            elif key in allowed:
                proposed_titles[key] = title or defaults[key]
    return [(key, proposed_titles.get(key, title)) for key, title in defaults.items()]


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

    validate_rows("module_introductions", "module_id", module_ids)
    validate_rows("finding_paragraphs", "finding_id", finding_ids)
    validate_rows("trend_paragraphs", "trend_id", trend_ids)
    validate_rows("scenario_paragraphs", "scenario_id", scenario_ids)
    plan = payload.get("section_plan")
    if plan is not None and not isinstance(plan, list):
        raise ReportGenerationError("正式报告章节计划结构无效")


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


def _first_dimension(dimensions: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _plain_report_prose(dimensions.get(key))
        if value:
            return value
    return ""


def _market_sizing_rows(module: Any) -> list[list[str]]:
    """Translate sizing workpaper fields into an auditable reader-facing formula table."""

    rows: list[list[str]] = []
    findings = getattr(module, "findings", []) if module is not None else []
    for finding in findings:
        if finding.review_status != AnalysisReviewStatus.ACCEPTED:
            continue
        dimensions = finding.comparison_dimensions or {}
        quantity = _first_dimension(
            dimensions,
            "quantity",
            "volume",
            "demand_quantity",
            "customer_count",
            "installed_base",
            "base_market",
        ) or "同口径销量、客户数、装机量或上级市场规模"
        unit_value = _first_dimension(
            dimensions,
            "weighted_average_price",
            "average_price",
            "unit_price",
            "unit_value",
            "share",
            "penetration_rate",
        ) or "同一价格层级的加权平均价格、单位价值或目标市场占比"
        formula = _first_dimension(dimensions, "formula", "calculation_formula", "sizing_formula")
        if not formula:
            formula = "分项规模＝数量端输入×价格或比例端输入"
        result = _first_dimension(dimensions, "result", "market_size", "subtotal")
        if not result and re.search(r"\d", finding.statement):
            result = finding.statement
        result = result or "分项计算后汇总为中心估计"
        de_duplication = _first_dimension(
            dimensions,
            "double_counting_rule",
            "overlap_rule",
            "market_boundary",
        ) or "按产品、客户与价值链口径去重，避免上下游收入重复加总"
        rows.append(
            [
                _plain_report_prose(finding.subject) or "目标市场",
                quantity,
                unit_value,
                formula,
                result,
                de_duplication,
            ]
        )
        if len(rows) >= 6:
            break
    if not rows:
        rows.append(
            [
                "目标市场",
                "同口径销量、客户数、装机量或上级市场规模",
                "加权平均价格、单位价值或目标市场占比",
                "市场规模＝Σ（分项数量×分项加权平均价格）",
                "分项加总形成中心估计与合理区间",
                "剔除上下游、存量与新增需求之间的重复统计",
            ]
        )
    return rows


def market_sizing_calculation_rows(analysis: Any) -> list[dict[str, str]]:
    """Expose the same sizing calculation chain in Reviewer workpapers."""

    module = next(
        (
            item
            for item in getattr(analysis, "modules", [])
            if getattr(item, "module_id", "") == "market_status"
        ),
        None,
    )
    labels = ("测算对象", "数量或规模输入", "价格或比例输入", "计算公式", "测算结果", "口径与去重规则")
    return [dict(zip(labels, row, strict=True)) for row in _market_sizing_rows(module)]


def _append_market_sizing_methodology(
    lines: list[str],
    module: Any,
    section_number: int,
) -> None:
    lines.extend([f"### {section_number}.1 市场规模测算方法与计算链", ""])
    _append_paragraphs(
        lines,
        (
            "本报告先统一产品与服务边界、地区、年份、收入或实物量、价格层级、税费以及新增、"
            "替换和服务需求口径，再选择最符合行业交易逻辑的主测算方法。自下而上测算以各细分"
            "产品或应用的数量乘以加权平均价格并加总；自上而下验证以上级市场规模乘以目标行业"
            "占比进行交叉检查。两种方法的差异通过定义、覆盖率、价格层级与重叠项解释，不作机械平均。"
        ),
    )
    lines.extend(
        [
            "| 测算对象 | 数量或规模输入 | 价格或比例输入 | 计算公式 | 测算结果 | 口径与去重规则 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in _market_sizing_rows(module):
        safe = [cell.replace("|", "／") for cell in row]
        lines.append("| " + " | ".join(safe) + " |")
    lines.append("")
    _append_paragraphs(
        lines,
        (
            "预测期不直接套用单一复合增长率，而是分别推演客户数量、销量或装机量、渗透率、"
            "配置率、替换率、价格及单位价值的变化，并通过历史序列、代表性企业收入或独立市场"
            "口径校验中心估计及合理区间。"
        ),
    )


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
    evidence_map = {item.evidence_id: item for item in accepted_evidence}
    source_numbers: dict[str, int] = {}
    ordered_sources = []
    for item in accepted_evidence:
        source = source_map.get(item.source_id)
        if source is None or source.source_id in source_numbers:
            continue
        source_numbers[source.source_id] = len(ordered_sources) + 1
        ordered_sources.append(source)

    def source_markers(evidence_ids: list[str]) -> str:
        numbers: list[int] = []
        for evidence_id in evidence_ids:
            evidence_item = evidence_map.get(evidence_id)
            if evidence_item is None:
                continue
            number = source_numbers.get(evidence_item.source_id)
            if number is not None and number not in numbers:
                numbers.append(number)
        if not numbers:
            return ""
        links = []
        for number in numbers:
            source = ordered_sources[number - 1]
            links.append(_markdown_link(str(number), source.url))
        return " " + " ".join(links)

    coverage = prompt_coverage or []
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

    scope_paragraph = _formal_paragraph(
        f"本报告研究对象为{project.region}的{project.industry}行业，研究时间范围为{project.time_horizon}",
        f"核心研究目标为{project.research_objective}",
    )
    lines: list[str] = [
        f"# {project.project_name}",
        "",
        scope_paragraph,
        "",
        "## 执行摘要",
        "",
    ]
    executive_summary = _plain_report_prose(
        narrative.get("executive_summary") if narrative else ""
    )
    if not executive_summary:
        executive_summary = _formal_paragraph(
            *[
                module.executive_summary
                for module in analysis.modules
                if any(
                    item.review_status == AnalysisReviewStatus.ACCEPTED
                    for item in module.findings
                )
            ]
        )
    _append_paragraphs(lines, executive_summary)

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
    module_map = {module.module_id: module for module in analysis.modules}

    def render_modules(
        module_ids: tuple[str, ...],
        section_number: int,
        *,
        start_subsection: int = 1,
    ) -> int:
        subsection = start_subsection
        for module_id in module_ids:
            module = module_map.get(module_id)
            if module is None:
                continue
            module_findings = [
                item for item in module.findings
                if item.review_status == AnalysisReviewStatus.ACCEPTED
            ]
            if not module_findings:
                continue
            intro = module_paragraphs.get(module.module_id) or module.executive_summary
            _append_paragraphs(lines, intro)
            for item in module_findings:
                fallback = _formal_paragraph(
                    item.statement,
                    item.mechanism,
                )
                paragraph = finding_paragraphs.get(item.finding_id) or fallback
                citations = source_markers([*item.evidence_ids, *item.counter_evidence_ids])
                lines.extend([f"### {section_number}.{subsection} {item.subject}", ""])
                _append_paragraphs(lines, paragraph + citations)
                subsection += 1
        return subsection
    section_plan = _report_section_plan(project, narrative)
    market_size_observations = [
        _plain_report_prose(item.statement)
        for item in accepted_evidence
        if re.search(r"\d", item.statement)
        and any(
            keyword in item.statement.lower()
            for keyword in ("市场规模", "亿元", "亿美元", "cagr", "复合增长率", "增速")
        )
    ][:2]
    section_numbers = {key: index for index, (key, _) in enumerate(section_plan, start=1)}
    for section_number, (section_key, section_title) in enumerate(section_plan, start=1):
        lines.extend(["", f"## {section_number}. {section_title}", ""])
        if section_key == "industry_definition":
            _append_paragraphs(lines, market_paragraph)
        elif section_key == "market_value_chain":
            render_modules(("market_value_chain", "commercial_logic"), section_number)
        elif section_key == "market_status":
            market_findings = module_map.get("market_status")
            _append_market_sizing_methodology(lines, market_findings, section_number)
            render_modules(("market_status",), section_number, start_subsection=2)
            market_text = " ".join(
                item.statement
                for item in (market_findings.findings if market_findings else [])
                if item.review_status == AnalysisReviewStatus.ACCEPTED
            )
            if not (
                re.search(r"\d", market_text)
                and any(
                    keyword in market_text.lower()
                    for keyword in ("市场规模", "亿元", "亿美元", "cagr", "复合增长率", "增速")
                )
            ) and market_size_observations:
                _append_paragraphs(
                    lines,
                    _formal_paragraph("市场规模测算方面", *market_size_observations),
                )
        elif section_key == "competitive_landscape":
            render_modules(("competitive_landscape",), section_number)
        elif section_key == "drivers_constraints":
            render_modules(("drivers_constraints",), section_number)

    method = future.forecast_methodology
    method_labels = {
        "causal_scenario": "因果情景",
        "naive_baseline": "朴素基准",
        "exponential_smoothing": "指数平滑",
        "trend_regression": "趋势回归",
        "regularized_driver_regression": "正则化驱动变量回归",
    }
    method_paragraph = _formal_paragraph(
        (
            f"本轮趋势预测采用{method_labels[method.selected_method.value]}方法，"
            f"结构化同口径历史观测共{method.structured_observation_count}期"
        ),
        method.selection_rationale,
        method.validation_design,
        method.prediction_interval,
    )
    future_section = section_numbers["future_outlook"]
    lines.extend([f"### {future_section}.1 预测方法", ""])
    _append_paragraphs(lines, method_paragraph)

    trend_subsection = 2
    for trend in accepted_trends:
        fallback = _formal_paragraph(
            trend.forecast_statement,
            f"该趋势的核心变化为{trend.core_trend or trend.title}，目标行业指标为{trend.target_industry_metric or '行业发展结果'}",
            f"该预测适用于{trend.forecast_horizon}，主要作用机制包括{'、'.join(trend.causal_mechanism)}，并直接影响{'、'.join(trend.direct_variables)}",
            f"正向作用为{trend.positive_effect}，反向作用为{trend.negative_effect}，供需动态反馈为{trend.dynamic_supply_demand_feedback}",
            f"相对基准情景的净影响为{trend.net_impact_summary}，市场规模影响评分为{trend.market_size_net_impact_score}，行业平均盈利能力影响评分为{trend.profitability_net_impact_score}",
            f"其对竞争格局的潜在影响为{trend.competition_impact}",
            f"其对商业模式的潜在影响为{trend.business_model_impact}",
            f"其对客户需求的潜在影响为{trend.customer_demand_impact}",
            f"短期、中期及长期方向分别为{trend.short_term_direction}、{trend.medium_term_direction}及{trend.long_term_direction}，方法置信度为{trend.method_confidence_score}分",
            f"持续验证指标包括{'、'.join(trend.verification_metrics)}",
            f"若出现{'、'.join(trend.falsification_conditions)}，则应重新评估该预测",
        )
        paragraph = trend_paragraphs.get(trend.trend_id) or fallback
        citations = source_markers(trend.evidence_ids)
        lines.extend([f"### {future_section}.{trend_subsection} {trend.title}", ""])
        _append_paragraphs(lines, paragraph + citations)
        trend_subsection += 1

    lines.extend([f"### {future_section}.{trend_subsection} 情景分析", ""])
    for scenario_index, scenario in enumerate(accepted_scenarios, start=1):
        fallback = _formal_paragraph(
            scenario.narrative,
            f"该情景的当前可能性判断为{scenario.likelihood_label}",
            f"其触发条件包括{'、'.join(scenario.trigger_conditions)}",
            f"若相关条件成立，预期结果包括{'、'.join(scenario.expected_outcomes)}",
            f"若出现{'、'.join(scenario.falsification_conditions)}，则该情景需要调整或失效",
        )
        lines.extend(
            [
                f"#### {future_section}.{trend_subsection}.{scenario_index} {_scenario_title(scenario.title)}",
                "",
            ]
        )
        _append_paragraphs(
            lines,
            scenario_paragraphs.get(scenario.scenario_id) or fallback,
        )

    lines.extend(["", "## 附录：资料来源", ""])
    for number, source in enumerate(ordered_sources, start=1):
        lines.append(f"[{number}] {_markdown_link(source.title, source.url)}。")
    unique_sources = {source_map[item.source_id].url for item in accepted_evidence}
    markdown = sanitize_formal_report("\n".join(lines))
    return GeneralReportArtifact(
        title=project.project_name,
        markdown=markdown,
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

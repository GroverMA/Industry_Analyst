"""Generate current-state industry analysis from human-accepted evidence only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError

from src.knowledge.sop import ResearchSOPPack
from src.models.analysis import (
    AnalysisFinding,
    AnalysisFindingType,
    AnalysisReviewStatus,
    FactorRole,
    ImpactDirection,
    IndustryAnalysisArtifact,
    IndustryAnalysisModule,
)
from src.models.evidence import EvidenceCollectionArtifact, EvidenceReviewStatus
from src.models.research import MethodologyTrace
from src.providers.base import ChatMessage, ModelResponse, ProviderError
from src.state.project import ProjectState


EXPECTED_MODULES = (
    "market_value_chain",
    "market_status",
    "competitive_landscape",
    "drivers_constraints",
    "commercial_logic",
)
MAX_ACCEPTED_EVIDENCE = 60


COMPETITION_SOP_DIRECTIVE = (
    "先锁定目标业务、指标、年份、地区、单位和币种，再建立宽口径候选公司池并映射各公司的"
    "实际目标业务。比较必须坚持同年、同地区、同细分业务、同指标、同单位和同币种；输出按"
    "行业排名或份额、候选池排序、竞争梯队或玩家类型、并列公司事实的顺序降级。正式判断须"
    "先给结论，再说明比较口径、玩家或梯队事实、结构差异及其行业含义；只要现有资料含有玩家、"
    "业务、份额、收入、产品或渠道事实，就不得生成空白竞争章节。"
)


DRIVERS_SOP_DIRECTIVE = (
    "必须从需求、供给、政策、技术、商业模式和竞争格局六个方向扫描影响因素，并把同一因果链"
    "上的重复信号合并。每项因素应形成‘事实变化—客户或系统要求—方案与采用变化—直接变量—"
    "市场规模或盈利指标—持续验证指标’的闭环，同时记录正反作用、供需反馈、短中长期方向、"
    "置信度与敏感假设。优先形成三至五项可直接进入报告的核心因素；资料有限时降低结论强度，"
    "不得留下空白驱动因素章节。"
)


class StructuredModel(Protocol):
    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        enable_thinking: bool = False,
    ) -> tuple[dict[str, Any], ModelResponse]: ...


class IndustryAnalysisError(ValueError):
    """Raised when analysis violates evidence or methodology boundaries."""


FINDING_CONTRACT = {
    "subject": "company, segment, value-chain stage, driver, or market",
    "finding_type": "fact_synthesis|source_viewpoint|analyst_inference|commercial_judgment",
    "statement": "current-state finding",
    "mechanism": "how the cited evidence supports the finding",
    "evidence_ids": ["EVD-..."],
    "counter_evidence_ids": ["EVD-..."],
    "comparison_dimensions": {"dimension": "observed comparison"},
    "factor_role": "driver|constraint|enabling_condition|mixed|conditional，非影响因素模块使用真正的JSON null",
    "impact_direction": "positive|negative|mixed|uncertain，非影响因素模块使用真正的JSON null",
    "confidence": 0.0,
    "scope": "applicable market and geography",
    "uncertainty": "known uncertainty",
    "boundary_condition": "condition under which the finding does not hold",
}

ANALYSIS_CONTRACT = {
    "modules": [
        {
            "module_id": "market_value_chain|market_status|competitive_landscape|drivers_constraints|commercial_logic",
            "title": "string",
            "executive_summary": "string",
            "findings": [FINDING_CONTRACT],
            "evidence_gaps": ["string"],
            "rejected_questions": ["questions that cannot be answered"],
        }
    ],
    "company_implications": [FINDING_CONTRACT],
    "cross_module_conflicts": ["string"],
    "overall_evidence_limitations": ["string"],
    "module_requirements": {
        "market_value_chain": "comparison_dimensions.value_chain_position",
        "competitive_landscape": "comparison_dimensions.relationship_type and comparison_basis",
        "drivers_constraints": "factor_role and impact_direction plus causal mechanism",
    },
}


class IndustryAnalysisService:
    def __init__(
        self,
        model: StructuredModel,
        sop: ResearchSOPPack,
    ) -> None:
        self.model = model
        self.sop = sop

    def generate(
        self,
        project: ProjectState,
        evidence_artifact: EvidenceCollectionArtifact,
    ) -> IndustryAnalysisArtifact:
        brief = project.research_brief_artifact
        if brief is None or not brief.human_confirmed:
            raise IndustryAnalysisError("Gate 0市场口径尚未确认")
        if not evidence_artifact.human_confirmed:
            raise IndustryAnalysisError("Evidence Matrix必须先经过人工批准")
        accepted = [
            item
            for item in evidence_artifact.evidence
            if item.review_status == EvidenceReviewStatus.ACCEPTED
        ]
        if not accepted:
            raise IndustryAnalysisError("没有可用于分析的已接受证据")
        accepted = self._select_evidence_with_question_coverage(accepted)

        source_map = {
            source.source_id: source for source in evidence_artifact.sources
        }
        evidence_payload = [
            {
                "evidence_id": item.evidence_id,
                "task_id": item.task_id,
                "kind": item.kind.value,
                "statement": item.statement,
                "supporting_excerpt": item.supporting_excerpt,
                "scope": f"{item.geographic_scope} · {item.market_scope}",
                "supports_or_challenges": item.supports_or_challenges,
                "qa_score": item.qa_score,
                "prompt_relevance": item.prompt_relevance,
                "task_question_ids": item.question_ids,
                "prompt_question_ids": item.prompt_question_ids,
                "source": {
                    "title": source_map[item.source_id].title,
                    "url": source_map[item.source_id].url,
                    "tier": source_map[item.source_id].source_tier.value,
                },
            }
            for item in accepted
        ]
        allowed_ids = {item.evidence_id for item in accepted}
        gap_context = {
            "resolution": evidence_artifact.coverage_gap_resolution,
            "user_input": evidence_artifact.coverage_gap_user_input,
            "handling_rule": (
                "用户补充内容只能作为待验证的专家观点或分析假设，不能作为公开事实证据；"
                "若公开资料覆盖有限，应使用最相关材料形成可审阅的分析师估计或样本判断，"
                "并把需要审阅者重点核对的内容留在内部evidence_gaps；不得因此输出空模块。"
            ),
        }
        modules = [
            self._generate_module(
                module_id,
                project,
                brief,
                evidence_payload,
                allowed_ids,
                gap_context,
            )
            for module_id in EXPECTED_MODULES
        ]
        limitations = []
        for module in modules:
            limitations.extend(module.get("evidence_gaps", []))
        payload = {
            "evidence_collection_id": evidence_artifact.artifact_id,
            "input_evidence_ids": sorted(allowed_ids),
            "modules": modules,
            # Company Scorecard and Action Plan are generated later from
            # confirmed enterprise inputs; the general industry layer must not
            # invent company-specific implications.
            "company_implications": [],
            "cross_module_conflicts": [],
            "overall_evidence_limitations": list(dict.fromkeys(limitations)),
            "methodology": self._trace().model_dump(),
        }
        self._validate_payload(payload, allowed_ids, False)
        return IndustryAnalysisArtifact.model_validate(payload)

    @staticmethod
    def _select_evidence_with_question_coverage(accepted: list) -> list:
        """Keep every represented question before applying the model-input cap."""

        ranked = sorted(
            accepted,
            key=lambda item: (item.qa_score, item.prompt_relevance),
            reverse=True,
        )
        required = {
            *(f"TASK:{value}" for item in ranked for value in item.question_ids),
            *(f"PROMPT:{value}" for item in ranked for value in item.prompt_question_ids),
        }
        selected: list = []
        selected_ids: set[str] = set()
        remaining = set(required)

        def coverage(item) -> set[str]:
            return {
                *(f"TASK:{value}" for value in item.question_ids),
                *(f"PROMPT:{value}" for value in item.prompt_question_ids),
            }

        while remaining and len(selected) < MAX_ACCEPTED_EVIDENCE:
            candidates = [
                item for item in ranked
                if item.evidence_id not in selected_ids and coverage(item) & remaining
            ]
            if not candidates:
                break
            chosen = max(
                candidates,
                key=lambda item: (
                    len(coverage(item) & remaining),
                    item.prompt_relevance,
                    item.qa_score,
                ),
            )
            selected.append(chosen)
            selected_ids.add(chosen.evidence_id)
            remaining -= coverage(chosen)
        for item in ranked:
            if len(selected) == MAX_ACCEPTED_EVIDENCE:
                break
            if item.evidence_id not in selected_ids:
                selected.append(item)
                selected_ids.add(item.evidence_id)
        return selected

    def _generate_module(
        self,
        module_id: str,
        project: ProjectState,
        brief,
        evidence_payload: list[dict[str, Any]],
        allowed_ids: set[str],
        gap_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate and repair one module without invalidating the other four."""

        module_task_ids = self._module_task_ids(project, module_id)
        module_evidence = [
            item for item in evidence_payload
            if not module_task_ids or item["task_id"] in module_task_ids
        ]
        if not module_evidence:
            module_evidence = evidence_payload
        elif module_id in {"competitive_landscape", "drivers_constraints"}:
            module_evidence = self._augment_cross_task_evidence(
                module_id,
                module_evidence,
                evidence_payload,
            )

        titles = {
            "market_value_chain": "市场定义、行业赛道与价值链",
            "market_status": "市场现状、规模与结构",
            "competitive_landscape": "竞争格局与可比公司",
            "drivers_constraints": "发展驱动、制约与关键条件",
            "commercial_logic": "商业逻辑与客户需求",
        }
        module_contract = {
            "module_id": module_id,
            "title": titles[module_id],
            "executive_summary": "string",
            "findings": [FINDING_CONTRACT],
            "evidence_gaps": ["string"],
            "rejected_questions": ["string"],
        }
        module_rules = {
            "market_value_chain": (
                "先形成行业范围定义，再分别研究赛道和产业链。赛道须使用同一分类维度建立"
                "上位行业、并列赛道、目标行业和子赛道，解释影响口径的交叉概念；产业链须沿"
                "真实产品、服务、数据与资金流拆解，区分直接客户、最终用户和应用，并解释各环节"
                "商业模式、价值、利润池、壁垒与风险。每项判断通过"
                "comparison_dimensions.value_chain_position说明位置。"
            ),
            "market_status": (
                "先统一对象、地区、年份、价值或实物量、价格、税费、业务以及新增/替换/服务口径。"
                "按行业经济逻辑选择Top-down、Bottom-up、枚举、新增配套加后市场或分应用加总作为"
                "主方法，并至少提出一种独立验证方法；说明公式、数据输入、假设、覆盖率、重叠、"
                "历史及预测结果与CAGR。每项市场规模判断的comparison_dimensions必须尽量写入"
                "quantity或base_market、weighted_average_price或share、formula、result、"
                "double_counting_rule及validation_method，使系统可以展示‘数量×价格’或‘上级市场"
                "×占比’的完整计算链。不得机械套用单一CAGR；输入不足时仍需使用合理代理形成中心"
                "估计与区间，并在内部底稿记录敏感变量，不得在正式报告写成无法测算。"
            ),
            "competitive_landscape": (
                COMPETITION_SOP_DIRECTIVE
                + "每个主体必须填写relationship_type与comparison_basis；有限样本不得称行业Top5或Top10。"
            ),
            "drivers_constraints": (
                DRIVERS_SOP_DIRECTIVE
                + "按机制区分driver、constraint、enabling_condition、mixed或conditional，并填写impact_direction。"
                "comparison_dimensions还须记录factor_class、temporal_role、positive_effect、"
                "negative_effect、supply_demand_feedback、market_size_score、profitability_score、"
                "short_medium_long_direction、confidence_1_to_5和sensitive_assumptions。"
            ),
            "commercial_logic": (
                "解释价值创造、付费方、客户需求、渠道、利润来源、风险与壁垒，"
                "不得越过证据生成未来预测或企业行动建议。"
            ),
        }[module_id]
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是Evidence-Grounded Industry Analyst。只能使用提供且已由用户接受的Evidence，"
                    "不得使用常识或训练记忆。事实综合、来源观点、分析师推断和商业判断必须分层。"
                    "每个模块必须至少形成一项可审阅判断。资料覆盖有限时，可基于最相关证据形成"
                    "分析师推断、区间估计或代表性样本判断，并降低confidence；不得输出空模块。"
                    "当前阶段不生成趋势、概率、资源配置建议或Action Plan。只输出合法JSON对象。\n\n"
                    + self.sop.prompt_context("analysis")
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"只生成模块：{module_id}（{titles[module_id]}）。{module_rules}\n"
                    f"项目：{project.project_name}\n行业：{project.industry}\n地区：{project.region}\n"
                    f"研究目标：{project.research_objective}\n时间范围：{project.time_horizon}\n"
                    "已确认Research Brief：\n"
                    f"{brief.model_dump_json(exclude={'methodology', 'generated_at'}, ensure_ascii=False)}\n\n"
                    f"已接受证据：\n{json.dumps(module_evidence, ensure_ascii=False)}\n\n"
                    "证据缺口人工处置：\n"
                    f"{json.dumps(gap_context, ensure_ascii=False)}\n\n"
                    f"严格输出一个module对象：\n{json.dumps(module_contract, ensure_ascii=False)}"
                ),
            ),
        ]
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                # The full SOP and structured contract already govern the
                # reasoning path.  Returning hidden chain-of-thought for each of
                # five modules substantially increases hosted-model latency and
                # is not needed by the workbench, which exposes the resulting
                # mechanism and trace fields instead.
                payload, _ = self.model.complete_json(messages, enable_thinking=False)
                module = self._extract_module(payload, module_id)
                wrapper = self._normalize_factor_fields({"modules": [module]})
                module = wrapper["modules"][0]
                self._validate_single_module(module, allowed_ids)
                return module
            except (ProviderError, IndustryAnalysisError, ValidationError) as exc:
                last_error = exc
                if isinstance(exc, ProviderError) and "timed out" in str(exc).lower():
                    break
                if attempt == 2:
                    break
                prior = json.dumps(
                    payload if "payload" in locals() else {},
                    ensure_ascii=False,
                )
                messages.extend(
                    [
                        ChatMessage(role="assistant", content=prior),
                        ChatMessage(
                            role="user",
                            content=(
                                f"该模块未通过结构或证据校验：{exc}。只修复{module_id}，"
                                "删除未知Evidence ID；资料覆盖有限时使用最相关Evidence形成一项"
                                "低置信度分析师推断，不得返回空findings。"
                                "重新输出完整module JSON对象。"
                            ),
                        ),
                    ]
                )
        return self._fallback_module(
            module_id,
            titles[module_id],
            module_evidence,
            last_error,
            project,
        )

    @staticmethod
    def _augment_cross_task_evidence(
        module_id: str,
        module_evidence: list[dict[str, Any]],
        all_evidence: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Reuse relevant accepted evidence across tasks for cross-cutting modules."""

        keywords = {
            "competitive_landscape": (
                "竞争", "企业", "公司", "玩家", "龙头", "市场份额", "市占", "产品线",
                "渠道", "罗氏", "雅培", "西门子", "丹纳赫", "迈瑞", "万孚", "安图",
            ),
            "drivers_constraints": (
                "需求", "供给", "政策", "集采", "监管", "技术", "创新", "增长", "驱动",
                "价格", "成本", "渠道", "商业模式", "国产", "替代", "老龄化", "渗透率",
            ),
        }[module_id]
        existing = {item["evidence_id"] for item in module_evidence}

        def relevance(item: dict[str, Any]) -> tuple[int, float, float]:
            text = f"{item.get('statement', '')} {item.get('supporting_excerpt', '')}".lower()
            return (
                sum(keyword.lower() in text for keyword in keywords),
                float(item.get("prompt_relevance", 0)),
                float(item.get("qa_score", 0)),
            )

        extras = [item for item in all_evidence if item["evidence_id"] not in existing]
        extras = [item for item in sorted(extras, key=relevance, reverse=True) if relevance(item)[0] > 0]
        return [*module_evidence, *extras[:12]]

    @staticmethod
    def _fallback_module(
        module_id: str,
        title: str,
        module_evidence: list[dict[str, Any]],
        last_error: Exception | None,
        project: ProjectState,
    ) -> dict[str, Any]:
        """Create a traceable reviewer draft when model JSON needs repair.

        This is deliberately conservative: it restates the strongest retrieved
        observation and labels the mechanism as an analyst interpretation.  It
        prevents a schema formatting error from erasing an entire report chapter.
        """

        keywords = {
            "market_value_chain": ("产业链", "上游", "下游", "赛道", "原材料"),
            "market_status": ("规模", "亿元", "亿美元", "cagr", "增速", "%"),
            "competitive_landscape": ("竞争", "份额", "企业", "公司", "玩家", "龙头"),
            "drivers_constraints": ("驱动", "政策", "需求", "增长", "集采", "技术"),
            "commercial_logic": ("客户", "渠道", "利润", "商业模式", "付费", "价格"),
        }[module_id]

        def score(item: dict[str, Any]) -> tuple[float, float, float]:
            text = f"{item.get('statement', '')} {item.get('supporting_excerpt', '')}".lower()
            keyword_hits = sum(keyword.lower() in text for keyword in keywords)
            return (
                float(keyword_hits),
                float(item.get("prompt_relevance", 0)),
                float(item.get("qa_score", 0)),
            )

        ranked = sorted(module_evidence, key=score, reverse=True)
        if not ranked:
            raise IndustryAnalysisError(f"{title}没有任何可追溯网页材料")
        selected_count = 4 if module_id in {"competitive_landscape", "drivers_constraints"} else 2
        selected = ranked[:selected_count]
        findings: list[dict[str, Any]] = []
        for item in selected:
            dimensions: dict[str, str] = {}
            factor_role = None
            impact_direction = None
            statement = str(item.get("statement") or item.get("supporting_excerpt") or "").strip()
            if module_id == "market_value_chain":
                dimensions["value_chain_position"] = "依据网页材料识别的行业环节或赛道位置"
            elif module_id == "competitive_landscape":
                dimensions.update(
                    {
                        "relationship_type": "直接竞争、替代竞争或可比参与者",
                        "comparison_basis": "同一目标市场中的产品、技术、客户、渠道、份额或业务活动",
                    }
                )
            elif module_id == "drivers_constraints":
                negative_markers = ("下降", "降价", "制约", "风险", "压力", "减少", "放缓", "集采")
                factor_role = (
                    FactorRole.CONSTRAINT.value
                    if any(marker in statement for marker in negative_markers)
                    else FactorRole.DRIVER.value
                )
                impact_direction = (
                    ImpactDirection.NEGATIVE.value
                    if factor_role == FactorRole.CONSTRAINT.value
                    else ImpactDirection.POSITIVE.value
                )
                dimensions.update(
                    {
                        "factor_class": "需求、供给、政策、技术、商业模式或竞争结构",
                        "temporal_role": "当前变化及其延续影响",
                        "positive_effect": "促进需求释放、供给改善、采用扩大或单位价值提升",
                        "negative_effect": "可能带来价格、成本、准入、替代或盈利压力",
                        "supply_demand_feedback": "供给能力、价格与需求采用之间形成动态反馈",
                        "market_size_score": "待结合影响范围与持续时间判断",
                        "profitability_score": "待结合价格、成本和竞争反应判断",
                        "short_medium_long_direction": "短期验证、中期扩散、长期结构化影响",
                        "confidence_1_to_5": "3",
                        "sensitive_assumptions": "政策执行、技术商业化、价格变化与客户采用速度",
                    }
                )
            findings.append(
                {
                    "subject": statement[:48] or title,
                    "finding_type": AnalysisFindingType.ANALYST_INFERENCE.value,
                    "statement": statement,
                    "mechanism": (
                        f"该可核验观察通过改变{project.region}{project.industry}的需求、供给、竞争或"
                        "单位经济性，形成可进入报告的行业判断；具体影响方向由其作用对象和边界条件限定。"
                    ),
                    "evidence_ids": [item["evidence_id"]],
                    "counter_evidence_ids": [],
                    "comparison_dimensions": dimensions,
                    "factor_role": factor_role,
                    "impact_direction": impact_direction,
                    "confidence": max(0.45, min(0.72, float(item.get("qa_score", 50)) / 100)),
                    "scope": f"{project.region} · {project.industry}",
                    "uncertainty": "公开资料的样本覆盖与整体市场之间仍需控制外推强度",
                    "boundary_condition": "若后续资料显示市场口径、时间或业务范围不同，应调整该判断",
                }
            )
        summary = "；".join(item["statement"] for item in findings[:3])
        return {
            "module_id": module_id,
            "title": title,
            "executive_summary": summary,
            "findings": findings,
            "evidence_gaps": [f"本模块由结构修复回退生成，需审阅者重点核对：{last_error}"],
            "rejected_questions": [],
        }

    @staticmethod
    def _module_task_ids(project: ProjectState, module_id: str) -> set[str]:
        plan = project.research_plan_artifact
        if plan is None:
            return set()
        module_keys = {
            "market_value_chain": (
                "industry_definition",
                "industry_track",
                "value_chain",
            ),
            "market_status": ("market_sizing", "industry_track"),
            "competitive_landscape": ("competitive_landscape",),
            "drivers_constraints": ("drivers_constraints",),
            # Commercial logic can draw from value-chain, competition and
            # driver evidence, so it intentionally receives the accepted set.
            "commercial_logic": (),
        }[module_id]
        return {
            task_id
            for key in module_keys
            for task_id in plan.sop_coverage.get(key, [])
        }

    @staticmethod
    def _extract_module(payload: dict[str, Any], module_id: str) -> dict[str, Any]:
        nested = payload.get("industry_analysis")
        if isinstance(nested, dict):
            payload = nested
        direct = payload.get("module")
        if isinstance(direct, dict):
            return direct
        modules = payload.get("modules")
        if isinstance(modules, list):
            match = next(
                (
                    item for item in modules
                    if isinstance(item, dict) and item.get("module_id") == module_id
                ),
                None,
            )
            if match is not None:
                return match
        if payload.get("module_id") == module_id:
            return payload
        raise IndustryAnalysisError(f"{module_id}模块缺失")

    @staticmethod
    def _validate_single_module(
        module: dict[str, Any],
        allowed_ids: set[str],
    ) -> None:
        module_id = module.get("module_id")
        if module_id not in EXPECTED_MODULES:
            raise IndustryAnalysisError("行业分析module_id缺失或无效")
        if not str(module.get("title") or "").strip() or not str(
            module.get("executive_summary") or ""
        ).strip():
            raise IndustryAnalysisError("模块标题或摘要不完整")
        findings = module.get("findings")
        gaps = module.get("evidence_gaps")
        if not isinstance(findings, list) or not isinstance(gaps, list):
            raise IndustryAnalysisError("模块findings或evidence_gaps结构无效")
        if not findings:
            raise IndustryAnalysisError("每个行业分析模块必须至少形成一项可审阅判断")
        if not isinstance(module.get("rejected_questions", []), list):
            raise IndustryAnalysisError("rejected_questions必须是数组")
        if module_id == "competitive_landscape":
            for finding in findings:
                dimensions = finding.get("comparison_dimensions", {})
                if not dimensions.get("relationship_type") or not dimensions.get(
                    "comparison_basis"
                ):
                    raise IndustryAnalysisError("竞争主体缺少关系类型或比较依据")
        if module_id == "drivers_constraints":
            for finding in findings:
                if finding.get("factor_role") not in {item.value for item in FactorRole}:
                    raise IndustryAnalysisError("发展条件与影响因素缺少factor_role")
                if finding.get("impact_direction") not in {
                    item.value for item in ImpactDirection
                }:
                    raise IndustryAnalysisError("发展条件与影响因素缺少impact_direction")
        valid_types = {item.value for item in AnalysisFindingType}
        for finding in findings:
            if not isinstance(finding, dict):
                raise IndustryAnalysisError("finding结构无效")
            ids = finding.get("evidence_ids")
            counter_ids = finding.get("counter_evidence_ids", [])
            if not isinstance(ids, list) or not ids:
                raise IndustryAnalysisError("每项行业判断必须引用Evidence ID")
            if not set(ids).issubset(allowed_ids) or not set(counter_ids).issubset(
                allowed_ids
            ):
                raise IndustryAnalysisError("行业分析引用了未知或未接受的Evidence ID")
            if finding.get("finding_type") not in valid_types:
                raise IndustryAnalysisError("行业分析finding_type无效")
            required = (
                "subject",
                "statement",
                "mechanism",
                "confidence",
                "scope",
                "uncertainty",
                "boundary_condition",
            )
            if any(
                key not in finding or finding[key] in (None, "")
                for key in required
            ):
                raise IndustryAnalysisError("行业分析finding字段不完整")
            try:
                AnalysisFinding.model_validate(finding)
            except ValidationError as exc:
                location = exc.errors()[0].get("loc", ("unknown",))
                raise IndustryAnalysisError(
                    f"行业分析finding字段类型无效：{location}"
                ) from exc
        try:
            IndustryAnalysisModule.model_validate(module)
        except ValidationError as exc:
            location = exc.errors()[0].get("loc", ("unknown",))
            raise IndustryAnalysisError(
                f"行业分析模块字段类型无效：{location}"
            ) from exc

    def _trace(self) -> MethodologyTrace:
        rules = [
            rule.rule_id
            for rule in self.sop.rules
            if "analysis" in rule.applies_to or "all" in rule.applies_to
        ]
        return MethodologyTrace(
            sop_id=self.sop.sop_id,
            sop_name=self.sop.display_name,
            sop_version=self.sop.version,
            sop_hash=self.sop.content_hash,
            locked=self.sop.locked,
            rule_ids=rules,
            compliance_checks=[
                "仅引用已接受Evidence ID",
                "事实、观点、推断和商业判断已分层",
                "行业赛道与产业链已区分",
                "市场规模方法、数据输入和缺口可追溯",
                "竞争格局使用同年同地区同业务同指标口径",
                "驱动与制约目标及因果链符合SOP",
                "竞争关系包含可解释的比较依据",
                "当前行业分析与未来趋势预测已分离",
            ],
        )

    @staticmethod
    def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
        nested = payload.get("industry_analysis")
        return nested if isinstance(nested, dict) else payload

    @staticmethod
    def _normalize_factor_fields(payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize harmless model formatting differences without inventing meaning."""

        aliases = {
            "驱动": "driver",
            "驱动因素": "driver",
            "增长动力": "driver",
            "制约": "constraint",
            "制约因素": "constraint",
            "限制因素": "constraint",
            "赋能条件": "enabling_condition",
            "有利条件": "enabling_condition",
            "发展条件": "enabling_condition",
            "混合": "mixed",
            "条件性": "conditional",
        }
        direction_aliases = {
            "正向": "positive",
            "积极": "positive",
            "促进": "positive",
            "负向": "negative",
            "消极": "negative",
            "抑制": "negative",
            "混合": "mixed",
            "双向": "mixed",
            "不确定": "uncertain",
        }
        modules = payload.get("modules")
        if not isinstance(modules, list):
            return payload
        for module in modules:
            if not isinstance(module, dict):
                continue
            findings = module.get("findings")
            if not isinstance(findings, list):
                continue
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                if not isinstance(finding.get("comparison_dimensions"), dict):
                    finding["comparison_dimensions"] = {}
                if not isinstance(finding.get("counter_evidence_ids"), list):
                    finding["counter_evidence_ids"] = []
                for key in ("factor_role", "impact_direction"):
                    value = finding.get(key)
                    if isinstance(value, str) and value.strip().lower() in {
                        "",
                        "null",
                        "none",
                        "n/a",
                        "na",
                        "not_applicable",
                        "不适用",
                        "无",
                    }:
                        finding[key] = None
                if module.get("module_id") != "drivers_constraints":
                    continue
                dimensions = finding["comparison_dimensions"]
                role = finding.get("factor_role") or finding.get("force_type") or dimensions.get("force_type")
                if isinstance(role, str):
                    normalized_role = role.strip()
                    finding["factor_role"] = aliases.get(
                        normalized_role,
                        normalized_role.lower(),
                    )
                if finding.get("factor_role") not in {item.value for item in FactorRole}:
                    finding["factor_role"] = FactorRole.CONDITIONAL.value
                direction = finding.get("impact_direction") or dimensions.get("impact_direction")
                if isinstance(direction, str) and direction.strip():
                    normalized_direction = direction.strip()
                    finding["impact_direction"] = direction_aliases.get(
                        normalized_direction,
                        normalized_direction.lower(),
                    )
                elif finding.get("factor_role") == FactorRole.DRIVER.value:
                    finding["impact_direction"] = ImpactDirection.POSITIVE.value
                elif finding.get("factor_role") == FactorRole.CONSTRAINT.value:
                    finding["impact_direction"] = ImpactDirection.NEGATIVE.value
                if finding.get("impact_direction") not in {
                    item.value for item in ImpactDirection
                }:
                    finding["impact_direction"] = ImpactDirection.UNCERTAIN.value
        return payload

    @staticmethod
    def _drop_unclassified_factor_findings(payload: dict[str, Any]) -> bool:
        """Degrade one malformed factor to an explicit gap, not a failed report."""

        valid_roles = {item.value for item in FactorRole}
        changed = False
        modules = payload.get("modules")
        if not isinstance(modules, list):
            return False
        for module in modules:
            if not isinstance(module, dict) or module.get("module_id") != "drivers_constraints":
                continue
            findings = module.get("findings")
            if not isinstance(findings, list):
                continue
            retained = [
                item for item in findings
                if isinstance(item, dict) and item.get("factor_role") in valid_roles
            ]
            removed = len(findings) - len(retained)
            if removed:
                module["findings"] = retained
                gaps = module.get("evidence_gaps")
                if not isinstance(gaps, list):
                    gaps = []
                    module["evidence_gaps"] = gaps
                gaps.append(f"{removed}项影响因素需要审阅者重新确认角色与方向")
                changed = True
        return changed

    @staticmethod
    def _validate_payload(
        payload: dict[str, Any],
        allowed_ids: set[str],
        has_target_company: bool,
    ) -> None:
        modules = payload.get("modules")
        if not isinstance(modules, list) or len(modules) != len(EXPECTED_MODULES):
            raise IndustryAnalysisError("必须完整输出五个行业分析模块")
        module_ids = [module.get("module_id") for module in modules if isinstance(module, dict)]
        if set(module_ids) != set(EXPECTED_MODULES) or len(module_ids) != len(set(module_ids)):
            raise IndustryAnalysisError("行业分析module_id缺失、重复或无效")
        all_findings: list[dict[str, Any]] = []
        for module in modules:
            findings = module.get("findings")
            gaps = module.get("evidence_gaps")
            if not isinstance(findings, list) or not isinstance(gaps, list):
                raise IndustryAnalysisError("模块findings或evidence_gaps结构无效")
            if not findings:
                raise IndustryAnalysisError("每个行业分析模块必须至少形成一项可审阅判断")
            if module["module_id"] == "competitive_landscape":
                for finding in findings:
                    dimensions = finding.get("comparison_dimensions", {})
                    if not dimensions.get("relationship_type") or not dimensions.get("comparison_basis"):
                        raise IndustryAnalysisError("竞争主体缺少关系类型或比较依据")
            if module["module_id"] == "drivers_constraints":
                for finding in findings:
                    if finding.get("factor_role") not in {item.value for item in FactorRole}:
                        raise IndustryAnalysisError("发展条件与影响因素缺少factor_role")
                    if finding.get("impact_direction") not in {item.value for item in ImpactDirection}:
                        raise IndustryAnalysisError("发展条件与影响因素缺少impact_direction")
            all_findings.extend(findings)

        company_implications = payload.get("company_implications", [])
        if not isinstance(company_implications, list):
            raise IndustryAnalysisError("company_implications必须是数组")
        if not has_target_company and company_implications:
            raise IndustryAnalysisError("无目标企业时不能虚构公司影响")
        all_findings.extend(company_implications)
        valid_types = {item.value for item in AnalysisFindingType}
        for finding in all_findings:
            if not isinstance(finding, dict):
                raise IndustryAnalysisError("finding结构无效")
            ids = finding.get("evidence_ids")
            counter_ids = finding.get("counter_evidence_ids", [])
            if not isinstance(ids, list) or not ids:
                raise IndustryAnalysisError("每项行业判断必须引用Evidence ID")
            if not set(ids).issubset(allowed_ids) or not set(counter_ids).issubset(allowed_ids):
                raise IndustryAnalysisError("行业分析引用了未知或未接受的Evidence ID")
            if finding.get("finding_type") not in valid_types:
                raise IndustryAnalysisError("行业分析finding_type无效")
            required = (
                "subject",
                "statement",
                "mechanism",
                "confidence",
                "scope",
                "uncertainty",
                "boundary_condition",
            )
            if any(key not in finding or finding[key] in (None, "") for key in required):
                raise IndustryAnalysisError("行业分析finding字段不完整")


def review_analysis_finding(
    artifact: IndustryAnalysisArtifact,
    finding_id: str,
    status: AnalysisReviewStatus,
    note: str | None = None,
) -> IndustryAnalysisArtifact:
    if status not in {AnalysisReviewStatus.ACCEPTED, AnalysisReviewStatus.REJECTED}:
        raise ValueError("analysis review can only accept or reject findings")
    found = False

    def reviewed(finding: AnalysisFinding) -> AnalysisFinding:
        nonlocal found
        if finding.finding_id != finding_id:
            return finding
        found = True
        return finding.model_copy(
            update={
                "review_status": status,
                "reviewer_note": note.strip() if note and note.strip() else None,
                "reviewed_at": datetime.now(UTC),
            }
        )

    modules = [
        module.model_copy(update={"findings": [reviewed(item) for item in module.findings]})
        for module in artifact.modules
    ]
    implications = [reviewed(item) for item in artifact.company_implications]
    if not found:
        raise ValueError(f"unknown analysis finding id: {finding_id}")
    return artifact.model_copy(
        update={
            "modules": modules,
            "company_implications": implications,
            "updated_at": datetime.now(UTC),
            "human_confirmed": False,
        }
    )


def analysis_gate_reasons(artifact: IndustryAnalysisArtifact | None) -> list[str]:
    if artifact is None:
        return ["尚未生成行业分析"]
    reasons: list[str] = []
    for module in artifact.modules:
        pending = [
            item for item in module.findings
            if item.review_status == AnalysisReviewStatus.NEEDS_REVIEW
        ]
        if pending:
            reasons.append(f"{module.title}仍有{len(pending)}项判断待审核")
        if not any(
            item.review_status == AnalysisReviewStatus.ACCEPTED
            for item in module.findings
        ):
            reasons.append(f"{module.title}尚无进入报告的已接受判断")
        if not module.findings and not module.evidence_gaps:
            reasons.append(f"{module.title}既无判断也无证据缺口记录")
    pending_company = [
        item for item in artifact.company_implications
        if item.review_status == AnalysisReviewStatus.NEEDS_REVIEW
    ]
    if pending_company:
        reasons.append(f"目标企业初步影响仍有{len(pending_company)}项待审核")
    if not any(
        item.review_status == AnalysisReviewStatus.ACCEPTED
        for item in artifact.findings
    ):
        reasons.append("尚无人工接受的行业判断")
    return reasons

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
        modules = [
            self._generate_module(
                module_id,
                project,
                brief,
                evidence_payload,
                allowed_ids,
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
    ) -> dict[str, Any]:
        """Generate and repair one module without invalidating the other four."""

        module_task_ids = self._module_task_ids(project, module_id)
        module_evidence = [
            item for item in evidence_payload
            if not module_task_ids or item["task_id"] in module_task_ids
        ]
        if not module_evidence:
            module_evidence = evidence_payload

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
                "同时区分行业赛道分类与上中下游价值链；每项判断通过"
                "comparison_dimensions.value_chain_position说明位置。"
            ),
            "market_status": (
                "在证据允许时说明市场规模口径与Top-down、Bottom-up或枚举法；"
                "无法测算时明确缺失数据、公式或假设。"
            ),
            "competitive_landscape": (
                "坚持同年、同地区、同细分业务、同指标；每个主体必须填写"
                "relationship_type与comparison_basis，不能因名称相似认定竞争。"
            ),
            "drivers_constraints": (
                "按机制区分driver、constraint、enabling_condition、mixed或conditional，"
                "并填写impact_direction、完整因果链、因素类型和可监测指标。"
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
                    "证据不足时findings必须为空，并在evidence_gaps中明确说明，不得编造。"
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
                    f"严格输出一个module对象：\n{json.dumps(module_contract, ensure_ascii=False)}"
                ),
            ),
        ]
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                payload, _ = self.model.complete_json(messages, enable_thinking=True)
                module = self._extract_module(payload, module_id)
                wrapper = self._normalize_factor_fields({"modules": [module]})
                module = wrapper["modules"][0]
                if module_id == "drivers_constraints":
                    self._drop_unclassified_factor_findings(wrapper)
                    module = wrapper["modules"][0]
                self._validate_single_module(module, allowed_ids)
                return module
            except (ProviderError, IndustryAnalysisError, ValidationError) as exc:
                last_error = exc
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
                                "删除未知Evidence ID；证据不足时用空findings和明确evidence_gaps。"
                                "重新输出完整module JSON对象。"
                            ),
                        ),
                    ]
                )
        return {
            "module_id": module_id,
            "title": titles[module_id],
            "executive_summary": "当前模块未形成可安全采用的结构化判断，已保留为明确证据缺口。",
            "findings": [],
            "evidence_gaps": [f"结构化生成未通过校验：{last_error}"],
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
        if not findings and not gaps:
            raise IndustryAnalysisError("无结论的模块必须明确记录证据缺口")
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
        """Normalize model formatting differences without inventing meaning."""

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
                dimensions = finding.get("comparison_dimensions")
                if not isinstance(dimensions, dict):
                    dimensions = {}
                    finding["comparison_dimensions"] = dimensions
                role = finding.get("factor_role") or finding.get("force_type") or dimensions.get("force_type")
                if isinstance(role, str):
                    normalized_role = role.strip()
                    finding["factor_role"] = aliases.get(
                        normalized_role,
                        normalized_role.lower(),
                    )
                direction = finding.get("impact_direction") or dimensions.get("impact_direction")
                if isinstance(direction, str) and direction.strip():
                    finding["impact_direction"] = direction.strip().lower()
                elif finding.get("factor_role") == FactorRole.DRIVER.value:
                    finding["impact_direction"] = ImpactDirection.POSITIVE.value
                elif finding.get("factor_role") == FactorRole.CONSTRAINT.value:
                    finding["impact_direction"] = ImpactDirection.NEGATIVE.value
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
                gaps.append(f"{removed}项影响因素因方向或角色无法可靠分类，未进入分析")
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
            if not findings and not gaps:
                raise IndustryAnalysisError("无结论的模块必须明确记录证据缺口")
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

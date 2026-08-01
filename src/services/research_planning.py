"""SOP-governed Research Brief and Research Plan generation."""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import ValidationError

from src.knowledge.sop import ResearchSOPPack
from src.models.research import (
    MethodologyTrace,
    ResearchBriefArtifact,
    ResearchPlanArtifact,
)
from src.providers.base import ChatMessage, ModelResponse
from src.state.project import ProjectState


class StructuredModel(Protocol):
    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        enable_thinking: bool = False,
    ) -> tuple[dict[str, Any], ModelResponse]: ...


class SOPComplianceError(ValueError):
    """Raised when a model artifact violates the active methodology pack."""


BRIEF_OUTPUT_CONTRACT = {
    "decision_statement": "string",
    "interpreted_intent": {
        "interpreted_objective": "string",
        "requested_topics": ["user-facing research topic"],
        "must_answer_questions": ["question that the final report must answer"],
        "terminology_map": {"user term": "semantic interpretation, not keyword match"},
        "explicit_exclusions": ["string"],
        "ambiguities": ["string"],
    },
    "market_definition": {
        "core_market": "string",
        "product_scope": "string",
        "customer_scope": "string",
        "geography_scope": "string",
        "value_chain_scope": "string",
        "time_scope": "string",
        "inclusions": ["string"],
        "exclusions": ["string"],
        "market_sizing_basis": "revenue/value/volume basis or unresolved",
        "competitor_definition": "substitution and comparison basis",
        "adjacent_markets": ["string"],
        "ambiguities": ["string"],
    },
    "key_questions": ["string"],
    "information_gaps": ["string"],
    "hypotheses": ["string"],
    "clarification_questions": ["string"],
    "confidence_note": "string",
}

PLAN_OUTPUT_CONTRACT = {
    "plan_summary": "string",
    "tasks": [
        {
            "task_id": "T01",
            "title": "string",
            "objective": "string",
            "questions": ["string"],
            "hypotheses": ["string"],
            "information_needs": ["string"],
            "preferred_sources": ["string"],
            "search_queries": ["string"],
            "deliverables": ["string"],
            "evidence_standard": "string",
            "counter_evidence_required": True,
            "validation_gate": "string",
            "depends_on": ["T00"],
            "prompt_question_ids": ["Q1"],
        }
    ],
    "human_review_gates": ["string"],
    "unresolved_gaps": ["string"],
    "sop_coverage": {
        "industry_definition": ["T01"],
        "industry_track": ["T01"],
        "value_chain": ["T02"],
        "market_sizing": ["T03"],
        "competitive_landscape": ["T04"],
        "drivers_constraints": ["T05"],
        "future_intelligence": ["T06"],
    },
    "prompt_question_coverage": {
        "Q1": ["T01"],
        "Q2": ["T02", "T04"],
    },
}


class ResearchPlanningService:
    def __init__(self, model: StructuredModel, sop: ResearchSOPPack) -> None:
        self.model = model
        self.sop = sop

    def generate_brief(self, project: ProjectState) -> ResearchBriefArtifact:
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是一名严谨的行业研究项目经理。当前研究方法包处于锁定状态，"
                    "必须逐条遵循，不能用通用模型习惯替代。不要编造市场事实；本步骤"
                    "只定义问题、边界、假设和信息缺口。业务决策是可选输入；如果用户"
                    "没有提供，不得虚构管理层决策，应将decision_statement写成清晰的"
                    "探索性研究目的。必须按语义理解用户表达：发展条件、增长动力、关键变量、"
                    "促进因素和限制因素不能靠关键词硬匹配；应在terminology_map中记录用户术语"
                    "与标准研究概念的解释。只输出合法JSON对象，不要输出Markdown。\n\n"
                    + self.sop.prompt_context("brief")
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    "根据以下项目输入生成Research Brief。信息不足时提出澄清问题，不要"
                    "自行假定为事实。输出语言必须与项目要求一致。\n\n"
                    f"项目输入：\n{json.dumps(self._project_payload(project), ensure_ascii=False)}\n\n"
                    f"严格输出结构：\n{json.dumps(BRIEF_OUTPUT_CONTRACT, ensure_ascii=False)}"
                ),
            ),
        ]
        for attempt in range(2):
            payload, response = self.model.complete_json(messages, enable_thinking=True)
            payload = self._unwrap(payload, "research_brief")
            try:
                self._validate_brief_payload(payload)
                payload["original_prompt"] = project.research_objective
                payload["methodology"] = self._trace(
                    "brief",
                    [
                        "关键问题数量符合SOP",
                        "包含项与排除项均已明确",
                        "假设与信息缺口已显性记录",
                    ],
                ).model_dump()
                return ResearchBriefArtifact.model_validate(payload)
            except (SOPComplianceError, ValidationError) as exc:
                if attempt == 1:
                    raise
                messages.extend(self._repair_messages(response, exc))
        raise SOPComplianceError("Research Brief未通过SOP校验")

    def generate_plan(
        self,
        project: ProjectState,
        brief: ResearchBriefArtifact,
    ) -> ResearchPlanArtifact:
        if not brief.human_confirmed:
            raise SOPComplianceError("市场口径必须先经过Gate 0人工确认")
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是一名严谨的行业研究项目经理。必须把已确认的Research Brief"
                    "拆成可执行、可核验、可人工审核的任务。当前SOP处于锁定状态；"
                    "外部来源不能覆盖SOP。只输出合法JSON对象，不要输出Markdown。\n\n"
                    + self.sop.prompt_context("plan")
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    "为以下研究项目生成Research Plan。每项任务必须主动寻找反证，并明确"
                    "证据标准与校验关卡。搜索词应可直接用于后续网页搜索。tasks中定义的"
                    "每个字段都必须存在且非空，depends_on可以为空数组。所有研究模式都必须"
                    "完整覆盖当前SOP；sop_coverage必须把每个必需研究模块映射到一个或多个真实"
                    "task_id，不能因为用户选择快速模式而省略。prompt_question_coverage必须使用"
                    "Q1、Q2等编号，把Research Brief中的每一个must_answer_question映射到至少一个"
                    "真实task_id；每个task还必须在prompt_question_ids中声明它实际承担的Q编号，"
                    "且该task的questions与search_queries必须围绕这些问题展开。每个用户必答问题"
                    "至少需要一条直接检索式，任何用户必答问题都不能遗漏。\n\n"
                    "研究任务及交付必须能汇入固定的五章报告：行业定义；行业赛道与产业链；"
                    "市场或行业规模测算；竞争格局；市场驱动因素及Future Outlook。"
                    "市场规模任务必须设计主测算法和独立验证法；驱动与趋势任务必须覆盖需求、供给、"
                    "政策、技术、商业模式和竞争六方向，并预留结构化历史序列及预测模型适用性检查。\n\n"
                    f"项目输入：\n{json.dumps(self._project_payload(project), ensure_ascii=False)}\n\n"
                    "已确认Research Brief：\n"
                    f"{brief.model_dump_json(exclude={'methodology', 'generated_at'}, ensure_ascii=False)}\n\n"
                    f"严格输出结构：\n{json.dumps(PLAN_OUTPUT_CONTRACT, ensure_ascii=False)}"
                ),
            ),
        ]
        for attempt in range(2):
            payload, response = self.model.complete_json(messages, enable_thinking=True)
            payload = self._unwrap(payload, "research_plan")
            try:
                self._validate_plan_payload(payload, brief)
                payload["methodology"] = self._trace(
                    "plan",
                    [
                        "研究任务数量符合SOP",
                        "全部任务包含证据标准与反证要求",
                        "原始Prompt中的每个必答问题均映射到执行任务",
                        "人工审核关卡数量符合SOP",
                    ],
                ).model_dump()
                return ResearchPlanArtifact.model_validate(payload)
            except (SOPComplianceError, ValidationError) as exc:
                if attempt == 1:
                    raise
                messages.extend(self._repair_messages(response, exc))
        raise SOPComplianceError("Research Plan未通过SOP校验")

    def _trace(self, artifact: str, checks: list[str]) -> MethodologyTrace:
        relevant_ids = [
            rule.rule_id
            for rule in self.sop.rules
            if artifact in rule.applies_to or "all" in rule.applies_to
        ]
        return MethodologyTrace(
            sop_id=self.sop.sop_id,
            sop_name=self.sop.display_name,
            sop_version=self.sop.version,
            sop_hash=self.sop.content_hash,
            locked=self.sop.locked,
            rule_ids=relevant_ids,
            compliance_checks=checks,
        )

    def _validate_brief_payload(self, payload: dict[str, Any]) -> None:
        constraints = self.sop.constraints
        questions = payload.get("key_questions")
        hypotheses = payload.get("hypotheses")
        market = payload.get("market_definition")
        intent = payload.get("interpreted_intent")
        if not isinstance(questions, list) or not (
            constraints.min_key_questions
            <= len(questions)
            <= constraints.max_key_questions
        ):
            raise SOPComplianceError("关键研究问题数量不符合当前SOP")
        if not isinstance(hypotheses, list) or len(hypotheses) < constraints.min_hypotheses:
            raise SOPComplianceError("研究假设数量不符合当前SOP")
        if constraints.require_inclusions_and_exclusions:
            if not isinstance(market, dict) or not market.get("inclusions") or not market.get("exclusions"):
                raise SOPComplianceError("当前SOP要求同时明确包含项和排除项")
        if not isinstance(intent, dict):
            raise SOPComplianceError("必须对用户原始Prompt进行语义解析")
        if not intent.get("interpreted_objective"):
            raise SOPComplianceError("Prompt语义解析缺少研究目标")
        if not intent.get("requested_topics") or not intent.get("must_answer_questions"):
            raise SOPComplianceError("必须提取用户要求的主题和报告必答问题")

    def _validate_plan_payload(
        self,
        payload: dict[str, Any],
        brief: ResearchBriefArtifact,
    ) -> None:
        constraints = self.sop.constraints
        tasks = payload.get("tasks")
        gates = payload.get("human_review_gates")
        if not isinstance(tasks, list) or not (
            constraints.min_tasks <= len(tasks) <= constraints.max_tasks
        ):
            raise SOPComplianceError("研究任务数量不符合当前SOP")
        if not isinstance(gates, list) or len(gates) < constraints.min_human_review_gates:
            raise SOPComplianceError("人工审核关卡数量不符合当前SOP")
        task_ids = [task.get("task_id") for task in tasks if isinstance(task, dict)]
        if len(task_ids) != len(tasks) or len(set(task_ids)) != len(task_ids):
            raise SOPComplianceError("研究任务必须具有唯一task_id")
        for task in tasks:
            if not isinstance(task, dict):
                raise SOPComplianceError("研究任务结构无效")
            if constraints.require_counter_evidence and task.get("counter_evidence_required") is not True:
                raise SOPComplianceError("当前SOP要求每项任务主动寻找反证")
            required = ("preferred_sources", "search_queries", "evidence_standard", "validation_gate")
            if any(not task.get(field) for field in required):
                raise SOPComplianceError("研究任务缺少来源、搜索、证据或校验要求")
        coverage = payload.get("sop_coverage")
        required_modules = set(constraints.required_research_modules)
        if required_modules:
            if not isinstance(coverage, dict) or not required_modules.issubset(coverage):
                raise SOPComplianceError("研究计划未完整覆盖当前SOP必需模块")
            valid_task_ids = set(task_ids)
            for module_id in required_modules:
                mapped = coverage.get(module_id)
                if (
                    not isinstance(mapped, list)
                    or not mapped
                    or not set(mapped).issubset(valid_task_ids)
                ):
                    raise SOPComplianceError(f"SOP模块{module_id}未映射到有效研究任务")

        prompt_coverage = payload.get("prompt_question_coverage")
        must_answer = brief.interpreted_intent.must_answer_questions or brief.key_questions
        required_question_ids = {f"Q{index}" for index in range(1, len(must_answer) + 1)}
        if not isinstance(prompt_coverage, dict) or not required_question_ids.issubset(
            prompt_coverage
        ):
            raise SOPComplianceError("研究计划遗漏了用户原始Prompt中的必答问题")
        valid_task_ids = set(task_ids)
        for question_id in required_question_ids:
            mapped = prompt_coverage.get(question_id)
            if (
                not isinstance(mapped, list)
                or not mapped
                or not set(mapped).issubset(valid_task_ids)
            ):
                raise SOPComplianceError(f"必答问题{question_id}未映射到有效研究任务")

        task_map = {task["task_id"]: task for task in tasks}
        for question_id in required_question_ids:
            for task_id in prompt_coverage[question_id]:
                declared = task_map[task_id].get("prompt_question_ids")
                if not isinstance(declared, list) or question_id not in declared:
                    raise SOPComplianceError(
                        f"任务{task_id}未声明其承担必答问题{question_id}"
                    )
        for task in tasks:
            declared = task.get("prompt_question_ids")
            if not isinstance(declared, list) or not declared:
                raise SOPComplianceError(
                    f"任务{task['task_id']}未连接到用户必答问题"
                )
            if not set(declared).issubset(required_question_ids):
                raise SOPComplianceError(
                    f"任务{task['task_id']}包含未知必答问题编号"
                )
            if len(task.get("search_queries", [])) < len(set(declared)):
                raise SOPComplianceError(
                    f"任务{task['task_id']}的检索式不足以逐项覆盖用户问题"
                )

    @staticmethod
    def _unwrap(payload: dict[str, Any], key: str) -> dict[str, Any]:
        nested = payload.get(key)
        return nested if isinstance(nested, dict) else payload

    @staticmethod
    def _project_payload(project: ProjectState) -> dict[str, Any]:
        return {
            "project_name": project.project_name,
            "industry": project.industry,
            "region": project.region,
            "target_company": project.target_company,
            "company_strategy_enabled": project.company_strategy_enabled,
            "company_strategy_objective": project.company_strategy_objective,
            "decision_context": project.decision_context,
            "research_objective": project.research_objective,
            "time_horizon": project.time_horizon,
            "output_language": project.output_language,
            "research_mode": project.research_mode.value,
            "industry_pack": project.industry_pack,
        }

    @staticmethod
    def _repair_messages(
        response: ModelResponse,
        error: SOPComplianceError | ValidationError,
    ) -> list[ChatMessage]:
        return [
            ChatMessage(role="assistant", content=response.content),
            ChatMessage(
                role="user",
                content=(
                    "上一次输出未通过锁定SOP和结构校验，不能降低标准。"
                    f"违规原因：{error}。请修复全部问题并重新输出完整JSON对象；"
                    "不要解释、不要省略任何字段。"
                ),
            ),
        ]

"""Iterative, report-first Reviewer revision workflow."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Protocol

from src.models.revision import (
    ContentRevisionArtifact,
    ReportVersion,
    RevisionTarget,
    RevisionTurn,
)
from src.providers.base import ChatMessage, ModelResponse, ProviderError
from src.services.report_generation import sanitize_formal_report
from src.state.project import ProjectState


class StructuredModel(Protocol):
    def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        enable_thinking: bool = False,
    ) -> tuple[dict[str, Any], ModelResponse]: ...


class ReviewerRevisionError(ValueError):
    pass


_H2_PATTERN = re.compile(r"(?m)^##\s+(.+?)\s*$")


def _revision_target_for_heading(title: str) -> RevisionTarget:
    """Map a deliverable chapter to the workpaper that owns it.

    The mapping is deliberately semantic rather than number based because the
    report outline is allowed to adapt to the user's prompt.  It is used as a
    write boundary: an AI revision may replace only chapters owned by a target
    explicitly selected by the reviewer.
    """

    normalized = re.sub(r"^\s*\d+(?:\.\d+)*[.、\s]*", "", title).strip().lower()
    if any(token in normalized for token in ("附录", "资料来源", "reference", "引用来源")):
        return RevisionTarget.REFERENCE_CHECK
    if any(
        token in normalized
        for token in (
            "company scorecard",
            "公司能力评分",
            "企业能力评分",
            "企业战略意图",
            "公司市场定位",
            "战略优势",
            "关键差距",
        )
    ):
        return RevisionTarget.COMPANY_SCORECARD
    if any(
        token in normalized
        for token in (
            "action plan",
            "行动计划",
            "战略行动",
            "推进顺序",
            "组合风险",
            "短期行动",
            "长期行动",
        )
    ):
        return RevisionTarget.ACTION_PLAN
    if any(token in normalized for token in ("future", "未来", "趋势", "情景", "展望", "预测")):
        return RevisionTarget.FUTURE_INTELLIGENCE
    return RevisionTarget.INDUSTRY_ANALYSIS


def _split_h2_sections(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    """Return the preamble and intact H2 chapter blocks."""

    matches = list(_H2_PATTERN.finditer(markdown))
    if not matches:
        return markdown, []
    preamble = markdown[: matches[0].start()]
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append((match.group(1).strip(), markdown[match.start() : end]))
    return preamble, sections


def merge_scoped_revision(
    current_markdown: str,
    proposed_markdown: str,
    targets: list[RevisionTarget],
) -> str:
    """Merge only selected report chapters and preserve all other bytes.

    REPORT is the sole target that authorizes a whole-document rewrite.  For
    every other target, the current report is the source of truth and proposed
    H2 chapters are spliced into the matching semantic slots.  This prevents a
    model from accidentally dropping scorecard/action-plan chapters while a
    reviewer is only changing Future Intelligence.
    """

    selected = set(targets)
    if not selected:
        raise ReviewerRevisionError("请至少选择一个本轮审阅范围")
    if RevisionTarget.REPORT in selected:
        return proposed_markdown

    current_preamble, current_sections = _split_h2_sections(current_markdown)
    _, proposed_sections = _split_h2_sections(proposed_markdown)
    if not current_sections:
        raise ReviewerRevisionError("当前报告缺少可识别的章节结构，请改选“完整报告”进行修订")

    replacement_sections = [
        block
        for title, block in proposed_sections
        if _revision_target_for_heading(title) in selected
    ]
    if not replacement_sections:
        labels = "、".join(item.value for item in targets)
        raise ReviewerRevisionError(f"AI未返回本轮选中模块（{labels}）的完整章节，请重试")

    output: list[str] = [current_preamble]
    inserted = False
    for title, block in current_sections:
        owner = _revision_target_for_heading(title)
        if owner in selected:
            if not inserted:
                output.extend(replacement_sections)
                inserted = True
            continue
        output.append(block)
    if not inserted:
        # The selected target may be a new optional chapter.  Insert it before
        # references so the appendix remains last.
        reference_index = next(
            (
                index
                for index, (title, _) in enumerate(current_sections)
                if _revision_target_for_heading(title) == RevisionTarget.REFERENCE_CHECK
            ),
            len(current_sections),
        )
        output = [current_preamble]
        for index, (_, block) in enumerate(current_sections):
            if index == reference_index:
                output.extend(replacement_sections)
            output.append(block)
        if reference_index == len(current_sections):
            output.extend(replacement_sections)
    return "".join(output)


def current_report(project: ProjectState):
    report = (
        project.enterprise_decision_report_artifact
        if project.company_strategy_enabled
        else project.general_report_artifact
    )
    if report is None:
        raise ReviewerRevisionError("请先生成完整报告")
    return report


def initialize_revision(project: ProjectState) -> ContentRevisionArtifact:
    report = current_report(project)
    existing = project.content_revision_artifact
    kind = "enterprise" if project.company_strategy_enabled else "general"
    if existing is not None and existing.report_kind == kind and existing.versions:
        return existing
    return ContentRevisionArtifact(
        project_id=project.project_id,
        report_kind=kind,
        versions=[ReportVersion(version=1, markdown=report.markdown, source="initial_draft")],
        active_version=1,
    )


def reviewer_attention_points(project: ProjectState) -> list[str]:
    """Keep research caveats inside the workbench, never in formal prose."""

    points: list[str] = []
    evidence = project.evidence_collection_artifact
    if evidence is not None:
        for item in evidence.evidence:
            if item.qa_score < 80 or item.prompt_relevance < 70:
                points.append(
                    f"{item.task_id}的部分材料质量或Prompt相关性低于建议阈值，需重点复核结论强度。"
                )
    analysis = project.industry_analysis_artifact
    if analysis is not None:
        for module in analysis.modules:
            if module.evidence_gaps:
                points.append(f"{module.title}包含需要重点复核的样本边界或结构修复结果。")
    future = project.future_intelligence_artifact
    if future is not None and future.forecast_gaps:
        points.append("Future Intelligence包含需要重点复核的假设、时间范围或情景敏感项。")
    return list(dict.fromkeys(points))[:12]


class ReviewerRevisionService:
    def __init__(self, model: StructuredModel) -> None:
        self.model = model

    def analyze(
        self,
        project: ProjectState,
        reviewer_message: str,
        targets: list[RevisionTarget],
        *,
        direct_draft: str | None = None,
    ) -> ContentRevisionArtifact:
        message = reviewer_message.strip()
        if not message:
            raise ReviewerRevisionError("请填写审阅意见或疑问")
        if not targets:
            raise ReviewerRevisionError("请至少选择一个本轮审阅范围")
        artifact = initialize_revision(project)
        report = current_report(project)
        analysis = project.industry_analysis_artifact
        future = project.future_intelligence_artifact
        evidence = project.evidence_collection_artifact
        context = {
            "original_prompt": project.research_objective,
            "market_scope": (
                project.research_brief_artifact.market_definition.model_dump(mode="json")
                if project.research_brief_artifact
                else {}
            ),
            "current_report": direct_draft.strip() if direct_draft and direct_draft.strip() else report.markdown,
            "reference_check": [
                {
                    "task": item.task_id,
                    "statement": item.statement,
                    "excerpt": item.supporting_excerpt,
                    "quality": item.qa_score,
                    "relevance": item.prompt_relevance,
                }
                for item in (evidence.evidence if evidence else [])[:50]
            ],
            "industry_analysis": [
                {
                    "module": module.title,
                    "summary": module.executive_summary,
                    "findings": [item.statement for item in module.findings],
                }
                for module in (analysis.modules if analysis else [])
            ],
            "future_intelligence": [
                {
                    "title": item.title,
                    "forecast": item.forecast_statement,
                    "mechanism": item.causal_mechanism,
                }
                for item in (future.trends if future else [])
            ],
            # Always send the enterprise strategy context.  When it is not in
            # the selected target list it becomes protected reference context,
            # not editable scope.
            "company_scorecard": (
                project.company_scorecard_artifact.model_dump(mode="json")
                if project.company_scorecard_artifact
                else None
            ),
            "action_plan": (
                project.action_plan_artifact.model_dump(mode="json")
                if project.action_plan_artifact
                else None
            ),
            "attention_points": reviewer_attention_points(project),
            "prior_turns": [
                {
                    "reviewer": turn.reviewer_message,
                    "assistant": turn.assistant_analysis,
                    "accepted": turn.accepted,
                }
                for turn in artifact.turns[-6:]
            ],
        }
        contract = {
            "assistant_analysis": "对审阅者问题的直接回应及与原始Prompt的重新对齐",
            "recommendations": ["建议采纳或保留的具体观点"],
            "questions_for_reviewer": ["只有确实需要审阅者判断时才提出的问题"],
            "trace_amendments": {
                "reference_check|industry_analysis|future_intelligence|company_scorecard|action_plan": (
                    "仅为本轮选中且确需调整的研究逻辑写出可追溯修订说明"
                )
            },
            "proposed_markdown": (
                "完整、可独立交付的新版本报告Markdown；只允许改变本轮选中模块，"
                "其余章节须逐字保留"
            ),
        }
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "你是行业研究报告的高级审阅编辑。先回到用户原始Prompt和已确认市场范围，分析"
                    "审阅者对报告、引用、行业分析、趋势、公司评分或行动计划提出的疑问，再给出"
                    "有立场、可解释的推荐观点，并生成一份完整的新版本报告。只有本轮审阅目标明确"
                    "选中的章节可以调整标题、顺序、篇幅和结论强度；所有未选章节属于锁定内容，必须"
                    "逐字保留，尤其不得删除或改写Company Scorecard和Action Plan。正式报告采用独立"
                    "第三方语气直接表达结论，不得出现内部ID、AI自述、系统流程、来源方叙述、证据缺口、"
                    "缺乏数据、无法量化、本模块只能覆盖、建议补充来源等措辞。市场规模必须给出估算值"
                    "或合理区间；无法直接获得时应以现有数字进行可解释的三角估算。审阅提醒只能出现在"
                    "assistant_analysis，不得进入proposed_markdown。只输出合法JSON。"
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"审阅目标：{json.dumps([item.value for item in targets], ensure_ascii=False)}\n"
                    f"审阅意见：{message}\n\n"
                    f"研究上下文：{json.dumps(context, ensure_ascii=False)}\n\n"
                    f"严格输出结构：{json.dumps(contract, ensure_ascii=False)}"
                ),
            ),
        ]
        try:
            payload, _ = self.model.complete_json(messages, enable_thinking=False)
        except ProviderError as exc:
            raise ReviewerRevisionError("AI审阅本轮未能完成，请保留意见后重试") from exc
        nested = payload.get("content_revision")
        if isinstance(nested, dict):
            payload = nested
        proposed_raw = sanitize_formal_report(str(payload.get("proposed_markdown") or ""))
        if len(proposed_raw) < 300:
            raise ReviewerRevisionError("AI返回的新版本报告不完整，请重试本轮审阅")
        current_markdown = (
            direct_draft.strip()
            if direct_draft and direct_draft.strip()
            else report.markdown
        )
        proposed = merge_scoped_revision(current_markdown, proposed_raw, targets)
        turn = RevisionTurn(
            reviewer_message=message,
            targets=targets or [RevisionTarget.REPORT],
            assistant_analysis=str(payload.get("assistant_analysis") or "已根据审阅意见重新分析报告。"),
            recommendations=[str(item) for item in payload.get("recommendations") or []],
            questions_for_reviewer=[str(item) for item in payload.get("questions_for_reviewer") or []],
            trace_amendments={
                str(key): str(value)
                for key, value in (payload.get("trace_amendments") or {}).items()
                if str(key) in {item.value for item in targets}
                and str(value).strip()
            },
            proposed_markdown=proposed,
        )
        return artifact.model_copy(
            update={
                "turns": [*artifact.turns, turn],
                "finalized": False,
                "updated_at": datetime.now(UTC),
            }
        )


def _with_report_markdown(project: ProjectState, markdown: str):
    report = current_report(project)
    updated_report = report.model_copy(
        update={"markdown": sanitize_formal_report(markdown), "generated_at": datetime.now(UTC)}
    )
    key = (
        "enterprise_decision_report_artifact"
        if project.company_strategy_enabled
        else "general_report_artifact"
    )
    return key, updated_report


def save_report_version(
    project: ProjectState,
    markdown: str,
    *,
    source: str,
    reviewer_note: str | None = None,
    accept_latest_turn: bool = False,
) -> ProjectState:
    artifact = initialize_revision(project)
    cleaned = sanitize_formal_report(markdown)
    if len(cleaned) < 300:
        raise ReviewerRevisionError("报告正文过短，无法保存为完整版本")
    version = len(artifact.versions) + 1
    turns = list(artifact.turns)
    if accept_latest_turn and turns:
        turns[-1] = turns[-1].model_copy(update={"accepted": True})
    artifact = artifact.model_copy(
        update={
            "versions": [
                *artifact.versions,
                ReportVersion(
                    version=version,
                    markdown=cleaned,
                    source=source,
                    reviewer_note=reviewer_note.strip() if reviewer_note and reviewer_note.strip() else None,
                ),
            ],
            "turns": turns,
            "active_version": version,
            "finalized": False,
            "updated_at": datetime.now(UTC),
        }
    )
    key, report = _with_report_markdown(project, cleaned)
    return project.model_copy(
        update={key: report, "content_revision_artifact": artifact, "updated_at": datetime.now(UTC)}
    )


def finalize_revision(project: ProjectState, finalized: bool = True) -> ProjectState:
    artifact = initialize_revision(project).model_copy(
        update={"finalized": finalized, "updated_at": datetime.now(UTC)}
    )
    return project.model_copy(
        update={"content_revision_artifact": artifact, "updated_at": datetime.now(UTC)}
    )

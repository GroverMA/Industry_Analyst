"""Compose the enterprise decision report from approved, traceable artifacts."""

from __future__ import annotations

import re

from src.models.strategy import EnterpriseDecisionReportArtifact, StrategyReviewStatus
from src.services.report_generation import sanitize_formal_report
from src.state.project import ProjectState


class StrategyReportError(ValueError):
    pass


def enterprise_report_gate_reasons(project: ProjectState) -> list[str]:
    reasons: list[str] = []
    if project.general_report_artifact is None:
        reasons.append("通用行业报告尚未生成")
    scorecard = project.company_scorecard_artifact
    if scorecard is None or not scorecard.human_confirmed:
        reasons.append("Company Scorecard尚未完成人工确认")
    action_plan = project.action_plan_artifact
    if action_plan is None or not action_plan.human_confirmed:
        reasons.append("Action Plan尚未完成人工确认")
    return reasons


def _generate_enterprise_decision_report_legacy(project: ProjectState) -> EnterpriseDecisionReportArtifact:
    reasons = enterprise_report_gate_reasons(project)
    if reasons:
        raise StrategyReportError("；".join(reasons))
    general = project.general_report_artifact
    scorecard = project.company_scorecard_artifact
    action_plan = project.action_plan_artifact
    assert general and scorecard and action_plan

    accepted_dimensions = [
        item for item in scorecard.dimensions
        if item.review_status == StrategyReviewStatus.ACCEPTED
    ]
    accepted_actions = [
        item for item in action_plan.actions
        if item.review_status == StrategyReviewStatus.ACCEPTED
    ]
    lines = [
        f"# {project.project_name} · 企业决策版",
        "",
        "> **报告状态：Human-reviewed Enterprise Decision Report**  ",
        "> 行业结论、公司评分和行动建议均经过人工阶段门确认；企业资料仅限本项目使用。",
        "",
        "## A. Management Decision Frame",
        "",
        f"- **目标企业：** {project.target_company}",
        f"- **战略意图：** {project.company_strategy_objective}",
        f"- **公司综合得分：** {scorecard.weighted_score if scorecard.weighted_score is not None else '证据覆盖不足，未计算'}",
        f"- **已评分权重覆盖：** {scorecard.scored_weight:.0%}",
        "",
        scorecard.overall_assessment,
        "",
        "## B. Company Scorecard",
        "",
        "| 维度 | 得分 | 权重 | 置信度 | 数据完整度 | Benchmark |",
        "|---|---:|---:|---:|---:|---|",
    ]
    benchmark_names = {item.benchmark_id: item.name for item in scorecard.benchmarks}
    for item in accepted_dimensions:
        benchmark = "、".join(benchmark_names.get(value, value) for value in item.benchmark_ids)
        score = f"{item.score:.1f}" if item.score is not None else "未评分"
        lines.append(
            f"| {item.title} | {score} | {item.weight:.0%} | {item.confidence}% | "
            f"{item.data_completeness}% | {benchmark or '—'} |"
        )
    lines.extend(["", "### 战略优势", ""])
    lines.extend(f"- {item}" for item in scorecard.strategic_advantages or ["未形成可接受判断"])
    lines.extend(["", "### 关键差距", ""])
    lines.extend(f"- {item}" for item in scorecard.critical_gaps or ["未形成可接受判断"])
    lines.extend(["", "### 跨维度风险", ""])
    lines.extend(f"- {item}" for item in scorecard.cross_dimension_risks or ["未形成可接受判断"])

    lines.extend(["", "## C. Approved Strategic Action Plan", ""])
    for index, action in enumerate(accepted_actions, start=1):
        lines.extend(
            [
                f"### C{index}. {action.title}",
                "",
                f"- **优先级：** {action.priority.value}",
                f"- **战略锚点：** {action.strategic_objective}",
                f"- **责任人：** {action.owner_role}",
                f"- **时间：** {action.timing}",
                f"- **理由：** {action.rationale}",
                f"- **资源：** {'；'.join(action.resources)}",
                f"- **依赖：** {'；'.join(action.dependencies) or '无额外依赖'}",
                f"- **风险：** {'；'.join(action.risks)}",
                f"- **缓解措施：** {'；'.join(action.mitigations)}",
                f"- **停止/转向条件：** {'；'.join(action.stop_conditions)}",
                f"- **置信度：** {action.confidence}%",
                f"- **不确定性：** {action.uncertainty}",
                f"- **追溯ID：** Score {', '.join(action.score_dimension_ids)} · "
                f"Public {', '.join(action.evidence_ids)} · Enterprise "
                f"{', '.join(action.enterprise_evidence_ids)} · Trend {', '.join(action.trend_ids)}",
                "",
                "| KPI类型 | 指标 | 定义 | 目标 | 时间 | 数据源 |",
                "|---|---|---|---|---|---|",
            ]
        )
        for kpi in action.kpis:
            lines.append(
                f"| {kpi.kpi_type.value} | {kpi.name} | {kpi.definition} | "
                f"{kpi.target} | {kpi.timing} | {kpi.data_source} |"
            )

    lines.extend(["", "## D. Sequencing and Portfolio Risks", "", "### 推进顺序", ""])
    lines.extend(f"- {item}" for item in action_plan.sequencing_logic)
    lines.extend(["", "### 未采纳选项", ""])
    lines.extend(f"- {item}" for item in action_plan.rejected_options or ["未记录"])
    lines.extend(["", "### 组合风险", ""])
    lines.extend(f"- {item}" for item in action_plan.portfolio_risks or ["未记录"])

    lines.extend(
        [
            "",
            "## E. Human Review & Responsibility Record",
            "",
            f"- Scorecard确认时间：{scorecard.confirmed_at or '未记录'}",
            f"- Action Plan确认时间：{action_plan.confirmed_at or '未记录'}",
            "- 责任边界：本报告为证据约束下的研究与决策支持，不替代企业管理层、法务、财务或临床责任人的最终判断。",
            "",
            "---",
            "",
            "# Appendix · General Industry Research",
            "",
            general.markdown,
        ]
    )
    return EnterpriseDecisionReportArtifact(
        title=f"{project.project_name} · 企业决策版",
        general_report_id=general.report_id,
        scorecard_id=scorecard.artifact_id,
        action_plan_id=action_plan.artifact_id,
        markdown="\n".join(lines),
    )


def _sentence(value) -> str:
    text = " ".join(str(value or "").split()).strip()
    text = re.sub(r"\b(?:EVD|FND|TRD|SCN|SRC|ENT|DIM|ACT)-[A-Za-z0-9_-]+\b", "", text)
    for symbol in ("➡", "➜", "→", "←", "👉", "👈"):
        text = text.replace(symbol, "")
    if text and text[-1] not in "。！？；.!?;":
        text += "。"
    return text


def _paragraph(*parts) -> str:
    return "".join(_sentence(part) for part in parts if str(part or "").strip())


def _split_general_report(markdown: str) -> tuple[str, str]:
    """Keep the six industry chapters in place and move references to the end."""

    body: list[str] = []
    references: list[str] = []
    in_references = False
    first_title_skipped = False
    for line in markdown.splitlines():
        if line.startswith("## 附录：资料来源"):
            in_references = True
            references.append(line)
            continue
        if not first_title_skipped and line.startswith("# "):
            first_title_skipped = True
            continue
        (references if in_references else body).append(line)
    return "\n".join(body).strip(), "\n".join(references).strip()


def generate_enterprise_decision_report(project: ProjectState) -> EnterpriseDecisionReportArtifact:
    """Compose the approved strategy layer as formal management-report prose."""

    reasons = enterprise_report_gate_reasons(project)
    if reasons:
        raise StrategyReportError("；".join(reasons))
    general = project.general_report_artifact
    scorecard = project.company_scorecard_artifact
    action_plan = project.action_plan_artifact
    assert general and scorecard and action_plan

    accepted_dimensions = [
        item for item in scorecard.dimensions
        if item.review_status == StrategyReviewStatus.ACCEPTED
    ]
    accepted_actions = [
        item for item in action_plan.actions
        if item.review_status == StrategyReviewStatus.ACCEPTED
    ]
    weighted_score = (
        f"{scorecard.weighted_score:.1f}分"
        if scorecard.weighted_score is not None
        else "按当前已评分维度暂不汇总"
    )
    general_body, general_references = _split_general_report(general.markdown)
    lines = [
        f"# {project.project_name} · 企业战略决策报告",
        "",
        _paragraph(
            f"本报告面向{project.target_company}的战略意图形成行业研究与企业决策支持",
            "报告先呈现行业定义、赛道与产业链、市场规模、竞争格局、驱动因素及未来展望，"
            "再结合企业能力形成评分、行动优先级和执行路径",
        ),
        "",
        general_body,
        "",
        "## 7. 企业战略意图与决策框架",
        "",
        _paragraph(
            f"目标企业为{project.target_company}",
            f"企业战略意图为{project.company_strategy_objective}",
            f"公司综合得分为{weighted_score}，已评分权重覆盖率为{scorecard.scored_weight:.0%}",
            scorecard.overall_assessment,
        ),
        "",
        "## 8. 公司能力评分",
        "",
        "| 评估维度 | 得分 | 公司当前市场位置 | 战略目标状态 | 核心差距 |",
        "|---|---:|---|---|---|",
    ]
    benchmark_names = {item.benchmark_id: item.name for item in scorecard.benchmarks}
    for item in accepted_dimensions:
        benchmark = "、".join(benchmark_names.get(value, value) for value in item.benchmark_ids)
        score = f"{item.score:.1f}" if item.score is not None else "未评分"
        lines.append(
            f"| {item.title} | {score} | {item.current_market_position} | "
            f"{item.target_position} | {item.strategic_gap} |"
        )
    lines.extend(
        [
            "",
            "### 8.1 战略优势",
            "",
            _paragraph(*(scorecard.strategic_advantages or ["当前评分显示企业优势仍处于培育阶段"])),
            "",
            "### 8.2 关键差距",
            "",
            _paragraph(*(scorecard.critical_gaps or ["当前评分未识别需要单独列示的关键能力差距"])),
            "",
            "### 8.3 跨维度风险",
            "",
            _paragraph(*(scorecard.cross_dimension_risks or ["当前评分未识别额外的跨维度风险"])),
            "",
            "## 9. 战略行动计划",
            "",
        ]
    )
    action_groups = (
        ("短期行动", [item for item in accepted_actions if item.timing != "长期"]),
        ("长期行动", [item for item in accepted_actions if item.timing == "长期"]),
    )
    for group_index, (group_title, group_actions) in enumerate(action_groups, start=1):
        if not group_actions:
            continue
        lines.extend([f"### 9.{group_index} {group_title}", ""])
        for action_index, action in enumerate(group_actions, start=1):
            lines.extend(
                [
                    f"#### 9.{group_index}.{action_index} {action.title}",
                    "",
                    _paragraph(
                        f"该项行动优先级为{action.priority.value}，并以{action.strategic_objective}为战略锚点",
                        f"建议由{action.owner_role}负责，作为{group_title}推进",
                        action.rationale,
                        f"所需资源包括{'、'.join(action.resources)}",
                        f"主要依赖包括{'、'.join(action.dependencies) if action.dependencies else '无额外依赖'}",
                        f"主要风险包括{'、'.join(action.risks)}，对应缓解措施包括{'、'.join(action.mitigations)}",
                        f"若出现{'、'.join(action.stop_conditions)}，应停止、调整或转向该项行动",
                        f"该建议置信度为{action.confidence}%，主要不确定性为{action.uncertainty}",
                    ),
                    "",
                    "| 指标类型 | 指标名称 | 指标定义 | 目标值 | 时间要求 | 数据来源 |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for kpi in action.kpis:
                lines.append(
                    f"| {kpi.kpi_type.value} | {kpi.name} | {kpi.definition} | "
                    f"{kpi.target} | {kpi.timing} | {kpi.data_source} |"
                )

    lines.extend(
        [
            "",
            "## 10. 推进顺序及组合风险",
            "",
            "### 10.1 推进顺序",
            "",
            _paragraph(*action_plan.sequencing_logic),
            "",
            "### 10.2 未采纳选项",
            "",
            _paragraph(*(action_plan.rejected_options or ["本轮审核未记录其他未采纳选项"])),
            "",
            "### 10.3 组合风险",
            "",
            _paragraph(*(action_plan.portfolio_risks or ["本轮审核未记录额外组合风险"])),
            "",
            "## 11. 人工审核及责任边界",
            "",
            _paragraph(
                f"公司评分确认时间为{scorecard.confirmed_at or '未记录'}",
                f"行动计划确认时间为{action_plan.confirmed_at or '未记录'}",
                (
                    "本报告属于证据约束下的研究与决策支持文件，不替代企业管理层、法务、财务、"
                    "临床或其他责任主体的最终判断"
                ),
            ),
            "",
            general_references,
        ]
    )
    markdown = sanitize_formal_report("\n".join(lines))
    return EnterpriseDecisionReportArtifact(
        title=f"{project.project_name} · 企业决策版",
        general_report_id=general.report_id,
        scorecard_id=scorecard.artifact_id,
        action_plan_id=action_plan.artifact_id,
        markdown=markdown,
    )

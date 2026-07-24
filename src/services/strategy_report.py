"""Compose the enterprise decision report from approved, traceable artifacts."""

from __future__ import annotations

from src.models.strategy import EnterpriseDecisionReportArtifact, StrategyReviewStatus
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


def generate_enterprise_decision_report(project: ProjectState) -> EnterpriseDecisionReportArtifact:
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
        f"- **业务决策：** {project.decision_context or '未指定单一业务决策'}",
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

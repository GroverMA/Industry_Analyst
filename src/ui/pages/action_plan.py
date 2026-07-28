"""Strategy-bound action plan generation and human review UI."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from src.models.strategy import KPIType, StrategyReviewStatus
from src.services.action_planning import (
    ActionPlanningError,
    action_plan_eligibility,
    action_plan_gate_reasons,
    confirm_action_plan,
    review_action,
)
from src.state.project import ProjectState, WorkflowStatus
from src.state.session import queue_page_navigation, set_project
from src.ui.agent_services import action_planning_service
from src.ui.components import badge, page_header, render_methodology_trace, require_project


def _save(project: ProjectState, artifact, *, status: WorkflowStatus) -> None:
    statuses = dict(project.workflow_status)
    statuses["action_plan"] = status
    statuses["decision_report"] = WorkflowStatus.NOT_STARTED
    updated = project.model_copy(
        update={
            "action_plan_artifact": artifact,
            "enterprise_decision_report_artifact": None,
            "workflow_status": statuses,
            "updated_at": datetime.now(UTC),
        }
    )
    set_project(st.session_state, updated)


def render(project: ProjectState | None) -> None:
    page_header(
        "07 · Action Plan",
        "把研究判断转化为可执行选择",
        "行动由企业战略意图决定方向，由公司评分、外部证据、企业一手信息和未来情景决定优先级与停止条件。",
    )
    if not require_project(project):
        return
    assert project is not None

    if not project.company_strategy_enabled:
        st.info("通用行业研究不生成某家公司的Action Plan，避免把行业趋势误写成企业战略建议。")
        if st.button("返回 Research Studio", width="stretch"):
            queue_page_navigation(st.session_state, "research_studio")
            st.rerun()
        return

    with st.container(border=True):
        st.markdown("#### 每项行动必须回扣的战略锚点")
        st.write(project.company_strategy_objective)
        st.caption("系统不会仅凭行业机会生成建议；没有企业资料与已确认公司评分时，本页保持锁定。")

    reasons = action_plan_eligibility(project)
    if reasons:
        st.warning("Action Plan仍锁定：\n\n" + "\n\n".join(f"- {reason}" for reason in reasons))
        if st.button("返回 Company Scorecard", width="stretch"):
            queue_page_navigation(st.session_state, "company_scorecard")
            st.rerun()
        return

    artifact = project.action_plan_artifact
    if artifact is None:
        st.success("Company Scorecard已确认，可以生成战略约束下的Action Plan。")
        if st.button("生成证据化 Action Plan", type="primary", width="stretch"):
            try:
                with st.spinner("模型正在形成行动组合，系统正在校验战略锚点、证据ID、KPI与停止条件…"):
                    artifact = action_planning_service().generate(project)
            except ActionPlanningError as exc:
                st.error(f"Action Plan生成失败：{exc}")
            else:
                _save(project, artifact, status=WorkflowStatus.NEEDS_REVIEW)
                st.rerun()
        return

    scorecard = project.company_scorecard_artifact
    if (
        scorecard is None
        or artifact.scorecard_id != scorecard.artifact_id
        or artifact.strategy_objective_snapshot != project.company_strategy_objective
    ):
        st.error("Company Scorecard或战略意图已变化，这版Action Plan已过期。")
        if st.button("清除过期 Action Plan", width="stretch"):
            _save(project, None, status=WorkflowStatus.READY)
            st.rerun()
        return

    accepted_count = sum(item.review_status == StrategyReviewStatus.ACCEPTED for item in artifact.actions)
    cols = st.columns(3)
    cols[0].metric("行动总数", len(artifact.actions))
    cols[1].metric("已接受", accepted_count)
    cols[2].metric("待审核", sum(item.review_status == StrategyReviewStatus.NEEDS_REVIEW for item in artifact.actions))

    with st.expander("组合排序逻辑与跨行动风险", expanded=True):
        st.markdown("**排序逻辑**")
        for item in artifact.sequencing_logic:
            st.write(f"- {item}")
        st.markdown("**暂不采用的战略选项**")
        for item in artifact.rejected_options or ["未记录"]:
            st.write(f"- {item}")
        st.markdown("**组合风险**")
        for item in artifact.portfolio_risks or ["未记录"]:
            st.write(f"- {item}")

    if any(item.review_status == StrategyReviewStatus.NEEDS_REVIEW for item in artifact.actions):
        col_a, col_b = st.columns(2)
        if col_a.button("批量接受全部行动", type="primary", width="stretch"):
            reviewed = artifact
            for item in artifact.actions:
                reviewed = review_action(reviewed, item.action_id, StrategyReviewStatus.ACCEPTED)
            _save(project, reviewed, status=WorkflowStatus.NEEDS_REVIEW)
            st.rerun()
        if col_b.button("批量拒绝全部行动", width="stretch"):
            reviewed = artifact
            for item in artifact.actions:
                reviewed = review_action(reviewed, item.action_id, StrategyReviewStatus.REJECTED)
            _save(project, reviewed, status=WorkflowStatus.NEEDS_REVIEW)
            st.rerun()

    for index, action in enumerate(artifact.actions, start=1):
        status_label = action.review_status.value.replace("_", " ").title()
        with st.expander(f"{index}. {action.title} · {action.priority.value.title()} · {status_label}", expanded=action.review_status == StrategyReviewStatus.NEEDS_REVIEW):
            st.markdown(
                badge(action.priority.value.title(), accent=True)
                + badge(f"Confidence {action.confidence}%")
                + badge(action.owner_role),
                unsafe_allow_html=True,
            )
            st.write("**战略锚点：** " + action.strategic_objective)
            st.write("**行动理由：** " + action.rationale)
            execution_cols = st.columns(3)
            execution_cols[0].write("**责任人**\n\n" + action.owner_role)
            execution_cols[1].write("**时间**\n\n" + action.timing)
            execution_cols[2].write("**资源**\n\n" + "；".join(action.resources))
            st.write("**依赖：** " + ("；".join(action.dependencies) or "无额外依赖"))
            st.markdown("**指标与决策阈值**")
            st.dataframe(
                [
                    {
                        "类型": "领先指标" if item.kpi_type == KPIType.LEADING else "结果指标",
                        "指标": item.name,
                        "定义": item.definition,
                        "目标/阈值": item.target,
                        "时间": item.timing,
                        "数据源": item.data_source,
                    }
                    for item in action.kpis
                ],
                width="stretch",
                hide_index=True,
            )
            risk_cols = st.columns(3)
            risk_cols[0].write("**主要风险**\n\n" + "\n\n".join(f"- {item}" for item in action.risks))
            risk_cols[1].write("**缓解措施**\n\n" + "\n\n".join(f"- {item}" for item in action.mitigations))
            risk_cols[2].write("**停止/转向条件**\n\n" + "\n\n".join(f"- {item}" for item in action.stop_conditions))
            st.caption("不确定性：" + action.uncertainty)
            st.caption(
                "Trace: Score " + "、".join(action.score_dimension_ids)
                + " · Public " + "、".join(action.evidence_ids)
                + " · Enterprise " + "、".join(action.enterprise_evidence_ids)
                + " · Trend " + "、".join(action.trend_ids)
            )
            note_key = f"action_note_{action.action_id}"
            st.session_state.setdefault(note_key, action.reviewer_note or "")
            note = st.text_input("审核备注", key=note_key)
            col_accept, col_reject = st.columns(2)
            if col_accept.button("接受该行动", type="primary", key=f"action_accept_{action.action_id}", width="stretch"):
                reviewed = review_action(artifact, action.action_id, StrategyReviewStatus.ACCEPTED, note)
                _save(project, reviewed, status=WorkflowStatus.NEEDS_REVIEW)
                st.rerun()
            if col_reject.button("拒绝该行动", key=f"action_reject_{action.action_id}", width="stretch"):
                reviewed = review_action(artifact, action.action_id, StrategyReviewStatus.REJECTED, note)
                _save(project, reviewed, status=WorkflowStatus.NEEDS_REVIEW)
                st.rerun()

    render_methodology_trace(artifact.methodology)
    gate_reasons = action_plan_gate_reasons(artifact)
    if gate_reasons:
        st.warning("Action Plan确认条件尚未满足：\n\n" + "\n\n".join(f"- {reason}" for reason in gate_reasons))
    if st.button("确认 Action Plan 并生成企业决策报告", type="primary", width="stretch"):
        try:
            confirmed = confirm_action_plan(artifact)
        except ActionPlanningError as exc:
            st.error(str(exc))
        else:
            statuses = dict(project.workflow_status)
            statuses["action_plan"] = WorkflowStatus.COMPLETED
            statuses["decision_report"] = WorkflowStatus.READY
            updated = project.model_copy(
                update={
                    "action_plan_artifact": confirmed,
                    "enterprise_decision_report_artifact": None,
                    "workflow_status": statuses,
                    "updated_at": datetime.now(UTC),
                }
            )
            set_project(st.session_state, updated)
            queue_page_navigation(st.session_state, "decision_report")
            st.rerun()

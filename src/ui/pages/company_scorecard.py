"""Evidence-bound company scorecard generation and human review UI."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from src.models.strategy import StrategyReviewStatus
from src.services.company_assessment import (
    CompanyAssessmentError,
    company_scorecard_eligibility,
    confirm_scorecard,
    review_score_dimension,
    scorecard_gate_reasons,
)
from src.state.project import ProjectState, WorkflowStatus
from src.state.session import queue_page_navigation, set_project
from src.ui.agent_services import company_assessment_service
from src.ui.components import badge, page_header, render_methodology_trace, require_project


def _save(project: ProjectState, artifact, *, status: WorkflowStatus) -> None:
    statuses = dict(project.workflow_status)
    statuses["company_assessment"] = status
    statuses["action_plan"] = WorkflowStatus.NOT_STARTED
    statuses["decision_report"] = WorkflowStatus.NOT_STARTED
    updated = project.model_copy(
        update={
            "company_scorecard_artifact": artifact,
            "action_plan_artifact": None,
            "enterprise_decision_report_artifact": None,
            "workflow_status": statuses,
            "updated_at": datetime.now(UTC),
        }
    )
    set_project(st.session_state, updated)


def render(project: ProjectState | None) -> None:
    page_header(
        "06 · Company Scorecard",
        "把行业变化映射到公司自身",
        "评分相对于明确Benchmark，并同时引用公开Evidence和经批准的企业一手Evidence；资料不足时不评分。",
    )
    if not require_project(project):
        return
    assert project is not None

    if not project.company_strategy_enabled:
        st.info("通用行业研究不会猜测企业能力。启用企业战略路径后，才会生成公司评分与行动建议。")
        if st.button("返回 Research Studio 启用企业定制分析", width="stretch"):
            queue_page_navigation(st.session_state, "research_studio")
            st.rerun()
        return

    with st.container(border=True):
        st.markdown("#### 评分对象与战略锚点")
        st.write(f"**目标企业：** {project.target_company}")
        st.write(f"**战略意图：** {project.company_strategy_objective}")
        st.caption("行业吸引力不等于企业竞争力；评分从行业关键趋势出发，判断公司当前市场位置、战略目标状态及两者之间的差距。")

    reasons = company_scorecard_eligibility(project)
    if reasons:
        st.warning("Company Scorecard仍锁定：\n\n" + "\n\n".join(f"- {reason}" for reason in reasons))
        col_a, col_b = st.columns(2)
        if col_a.button("返回研究主流程", width="stretch"):
            queue_page_navigation(st.session_state, "research_studio")
            st.rerun()
        if col_b.button("完善 Enterprise Sensing", width="stretch"):
            queue_page_navigation(st.session_state, "enterprise_sensing")
            st.rerun()
        return

    artifact = project.company_scorecard_artifact
    if artifact is None:
        st.success("评分所需的战略目标、企业一手资料、外部证据、行业判断与未来趋势均已通过阶段门。")
        if st.button("生成证据化 Company Scorecard", type="primary", width="stretch"):
            try:
                with st.spinner("模型正在相对Benchmark分析企业能力，系统正在计算分数、覆盖度与置信度…"):
                    artifact = company_assessment_service().generate(project)
            except CompanyAssessmentError as exc:
                st.error(f"Company Scorecard生成失败：{exc}")
            else:
                _save(project, artifact, status=WorkflowStatus.NEEDS_REVIEW)
                st.rerun()
        return

    if (
        artifact.target_company_snapshot != project.target_company
        or artifact.strategy_objective_snapshot != project.company_strategy_objective
    ):
        st.error("目标企业或战略意图已变化，这版评分已过期。请重新生成。")
        if st.button("清除过期评分", width="stretch"):
            _save(project, None, status=WorkflowStatus.READY)
            st.rerun()
        return

    st.subheader("评分总览")
    cols = st.columns(3)
    cols[0].metric("综合得分", f"{artifact.weighted_score:.1f}" if artifact.weighted_score is not None else "未计算")
    cols[1].metric("有证据评分覆盖", f"{artifact.scored_weight:.0%}")
    cols[2].metric("已审核维度", f"{sum(item.review_status != StrategyReviewStatus.NEEDS_REVIEW for item in artifact.dimensions)}/6")
    st.write(artifact.overall_assessment)

    with st.expander("Benchmark定义与依据", expanded=True):
        for item in artifact.benchmarks:
            st.markdown(f"**{item.name}** · {item.benchmark_type.value}")
            st.write(item.rationale)
            st.caption("Evidence: " + "、".join(item.evidence_ids))

    if any(item.review_status == StrategyReviewStatus.NEEDS_REVIEW for item in artifact.dimensions):
        if st.button("批量采用有证据评分，并拒绝未评分维度", width="stretch"):
            reviewed = artifact
            for item in artifact.dimensions:
                status = StrategyReviewStatus.ACCEPTED if item.score is not None else StrategyReviewStatus.REJECTED
                reviewed = review_score_dimension(reviewed, item.dimension_id, status)
            _save(project, reviewed, status=WorkflowStatus.NEEDS_REVIEW)
            st.rerun()

    benchmark_names = {item.benchmark_id: item.name for item in artifact.benchmarks}
    for item in artifact.dimensions:
        score_label = f"{item.score:.1f}/100" if item.score is not None else "未评分"
        status_label = item.review_status.value.replace("_", " ").title()
        with st.expander(f"{item.title} · {score_label} · {status_label}", expanded=item.review_status == StrategyReviewStatus.NEEDS_REVIEW):
            st.markdown(
                badge(f"Weight {item.weight:.0%}")
                + badge(f"Confidence {item.confidence}%", accent=True)
                + badge(f"Data {item.data_completeness}%"),
                unsafe_allow_html=True,
            )
            if item.score_components:
                components = item.score_components
                component_cols = st.columns(4)
                component_cols[0].metric("当前能力", f"{components.current_capability}/5")
                component_cols[1].metric("Benchmark位置", f"{components.benchmark_position}/5")
                component_cols[2].metric("战略适配", f"{components.strategic_fit}/5")
                component_cols[3].metric("未来准备", f"{components.future_readiness}/5")
            else:
                st.warning(item.unscored_reason or "资料不足，系统未评分")
            st.write("**评分理由：** " + item.score_rationale)
            st.write("**行业趋势与维度意义：** " + item.industry_relevance)
            st.write("**公司当前市场位置：** " + item.current_market_position)
            st.write("**战略目标状态：** " + item.target_position)
            st.write("**当前—目标差距：** " + item.strategic_gap)
            st.write("**战略适配解释：** " + item.strategic_fit_explanation)
            st.write("**Benchmark：** " + "、".join(benchmark_names.get(value, value) for value in item.benchmark_ids))
            st.write("**优势：** " + ("；".join(item.strengths) or "未识别"))
            st.write("**差距：** " + ("；".join(item.gaps) or "未识别"))
            st.write("**风险：** " + ("；".join(item.risks) or "未识别"))
            st.caption(
                "Public Evidence: " + ("、".join(item.external_evidence_ids) or "无")
                + " · Enterprise Evidence: " + ("、".join(item.enterprise_evidence_ids) or "无")
            )
            st.caption("不确定性：" + item.uncertainty)
            note_key = f"score_note_{item.dimension_id}"
            st.session_state.setdefault(note_key, item.reviewer_note or "")
            note = st.text_input("审核备注", key=note_key)
            col_accept, col_reject = st.columns(2)
            if col_accept.button("接受该维度", type="primary", key=f"score_accept_{item.dimension_id}", width="stretch", disabled=item.score is None):
                reviewed = review_score_dimension(artifact, item.dimension_id, StrategyReviewStatus.ACCEPTED, note)
                _save(project, reviewed, status=WorkflowStatus.NEEDS_REVIEW)
                st.rerun()
            if col_reject.button("拒绝该维度", key=f"score_reject_{item.dimension_id}", width="stretch"):
                reviewed = review_score_dimension(artifact, item.dimension_id, StrategyReviewStatus.REJECTED, note)
                _save(project, reviewed, status=WorkflowStatus.NEEDS_REVIEW)
                st.rerun()

    render_methodology_trace(artifact.methodology)
    gate_reasons = scorecard_gate_reasons(artifact)
    if gate_reasons:
        st.warning("评分确认条件尚未满足：\n\n" + "\n\n".join(f"- {reason}" for reason in gate_reasons))
    if st.button("确认 Company Scorecard 并进入 Action Plan", type="primary", width="stretch"):
        try:
            confirmed = confirm_scorecard(artifact)
        except CompanyAssessmentError as exc:
            st.error(str(exc))
        else:
            statuses = dict(project.workflow_status)
            statuses["company_assessment"] = WorkflowStatus.COMPLETED
            statuses["action_plan"] = WorkflowStatus.READY
            statuses["decision_report"] = WorkflowStatus.NOT_STARTED
            updated = project.model_copy(
                update={
                    "company_scorecard_artifact": confirmed,
                    "action_plan_artifact": None,
                    "enterprise_decision_report_artifact": None,
                    "workflow_status": statuses,
                    "updated_at": datetime.now(UTC),
                }
            )
            set_project(st.session_state, updated)
            queue_page_navigation(st.session_state, "action_plan")
            st.rerun()

"""General and enterprise decision report delivery UI."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from src.services.report_export import (
    build_report_docx,
    build_report_pdf,
    project_report_context,
)
from src.services.strategy_report import (
    StrategyReportError,
    enterprise_report_gate_reasons,
    generate_enterprise_decision_report,
)
from src.state.project import ProjectState, WorkflowStatus
from src.state.session import ACTIVE_PAGE_KEY, set_project
from src.ui.components import page_header, require_project


def _safe_name(value: str) -> str:
    return "-".join(value.split()) or "industry-report"


def render(project: ProjectState | None) -> None:
    page_header(
        "08 · Decision Report",
        "下载通用行业报告或企业决策报告",
        "通用报告回答行业问题；企业决策版在其上叠加经人工确认的公司评分、战略行动、KPI、风险与停止条件。",
    )
    if not require_project(project):
        return
    assert project is not None

    general = project.general_report_artifact
    if general is None:
        st.warning("通用报告尚未生成。请在Research Studio依次完成市场口径、证据和报告内容审核。")
        if st.button("返回 Research Studio", type="primary", width="stretch"):
            st.session_state[ACTIVE_PAGE_KEY] = "research_studio"
            st.rerun()
        return

    st.subheader("A. 通用行业研究报告")
    st.success("适用于不提供企业资料的用户，也可作为企业决策版的行业研究底稿。")
    cols = st.columns(3)
    cols[0].metric("采用证据", len(general.accepted_evidence_ids))
    cols[1].metric("采用判断", len(general.accepted_finding_ids))
    cols[2].metric("独立来源", general.source_count)
    with st.expander("预览通用行业报告", expanded=not project.company_strategy_enabled):
        st.markdown(general.markdown)
    safe_name = _safe_name(project.project_name)
    general_context = project_report_context(
        project,
        title=general.title,
        markdown=general.markdown,
        report_status="经人工审核的通用行业研究报告",
        generated_at=general.generated_at,
    )
    col_a, col_b = st.columns(2)
    col_a.download_button(
        "下载通用报告 Word",
        data=build_report_docx(general_context),
        file_name=f"{safe_name}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        width="stretch",
        type="primary",
    )
    col_b.download_button(
        "下载通用报告 PDF",
        data=build_report_pdf(general_context),
        file_name=f"{safe_name}.pdf",
        mime="application/pdf",
        width="stretch",
        type="primary",
    )

    if not project.company_strategy_enabled:
        st.info("当前为通用行业研究路径，因此报告不包含Company Scorecard与Action Plan。")
        return

    st.divider()
    st.subheader("B. 企业决策报告")
    st.caption("只有公司评分和Action Plan都通过人工审核后，才会把企业资料与行业结论合并为决策版报告。")
    reasons = enterprise_report_gate_reasons(project)
    if reasons:
        st.warning("企业决策版尚未就绪：\n\n" + "\n\n".join(f"- {reason}" for reason in reasons))
        navigation = st.columns(2)
        if navigation[0].button("查看 Company Scorecard", width="stretch"):
            st.session_state[ACTIVE_PAGE_KEY] = "company_scorecard"
            st.rerun()
        if navigation[1].button("查看 Action Plan", width="stretch"):
            st.session_state[ACTIVE_PAGE_KEY] = "action_plan"
            st.rerun()
        return

    enterprise_report = project.enterprise_decision_report_artifact
    scorecard = project.company_scorecard_artifact
    action_plan = project.action_plan_artifact
    assert scorecard and action_plan
    report_is_stale = bool(
        enterprise_report
        and (
            enterprise_report.scorecard_id != scorecard.artifact_id
            or enterprise_report.action_plan_id != action_plan.artifact_id
            or enterprise_report.general_report_id != general.report_id
        )
    )
    if enterprise_report is None or report_is_stale:
        if report_is_stale:
            st.warning("上游评分、行动计划或通用报告已更新，需要重新生成企业决策版。")
        if st.button("生成 Enterprise Decision Report", type="primary", width="stretch"):
            try:
                enterprise_report = generate_enterprise_decision_report(project)
            except StrategyReportError as exc:
                st.error(str(exc))
            else:
                statuses = dict(project.workflow_status)
                statuses["decision_report"] = WorkflowStatus.COMPLETED
                updated = project.model_copy(
                    update={
                        "enterprise_decision_report_artifact": enterprise_report,
                        "workflow_status": statuses,
                        "updated_at": datetime.now(UTC),
                    }
                )
                set_project(st.session_state, updated)
                st.rerun()
        return

    st.success("企业决策报告已生成：行业底稿、公司评分和行动建议均保留追溯ID与人工审核记录。")
    with st.expander("预览企业决策报告", expanded=True):
        st.markdown(enterprise_report.markdown)
    enterprise_context = project_report_context(
        project,
        title=enterprise_report.title,
        markdown=enterprise_report.markdown,
        report_status="经人工审核的企业战略决策报告",
        generated_at=enterprise_report.generated_at,
    )
    col_c, col_d = st.columns(2)
    col_c.download_button(
        "下载企业决策报告 Word",
        data=build_report_docx(enterprise_context),
        file_name=f"{safe_name}.enterprise-decision.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        width="stretch",
        type="primary",
    )
    col_d.download_button(
        "下载企业决策报告 PDF",
        data=build_report_pdf(enterprise_context),
        file_name=f"{safe_name}.enterprise-decision.pdf",
        mime="application/pdf",
        width="stretch",
        type="primary",
    )

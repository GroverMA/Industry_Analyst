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
from src.state.session import queue_page_navigation, set_project
from src.ui.components import page_header, require_project
from src.ui.report_preview import render_report_preview


def _safe_name(value: str) -> str:
    return "-".join(value.split()) or "industry-report"


def render(project: ProjectState | None) -> None:
    if project is not None and project.company_strategy_enabled:
        page_header(
            "Enterprise Report",
            "企业战略决策报告",
            "把行业研究底稿、企业一手资料、公司评分和Action Plan整合为可追溯的企业决策报告。",
        )
    else:
        page_header(
            "Decision Report",
            "通用行业研究报告",
            "通用报告回答行业现状、竞争格局、驱动因素与未来趋势，并提供Word和PDF版本。",
        )
    if not require_project(project):
        return
    assert project is not None

    general = project.general_report_artifact
    if general is None:
        st.warning("通用报告尚未生成。请在Research Studio依次完成市场口径、证据和报告内容审核。")
        if st.button("返回 Research Studio", type="primary", width="stretch"):
            queue_page_navigation(st.session_state, "research_studio")
            st.rerun()
        return

    safe_name = _safe_name(project.project_name)
    if not project.company_strategy_enabled:
        st.subheader("通用行业研究报告")
        cols = st.columns(3)
        cols[0].metric("采用证据", len(general.accepted_evidence_ids))
        cols[1].metric("采用判断", len(general.accepted_finding_ids))
        cols[2].metric("独立来源", general.source_count)
        render_report_preview(
            general.markdown,
            key=f"decision_general_{project.project_id}",
            expanded=True,
            label="预览通用行业报告",
        )
        general_context = project_report_context(
            project,
            title=general.title,
            markdown=general.markdown,
            report_status="经人工审核的通用行业研究报告",
            generated_at=general.generated_at,
        )
        col_a, col_b = st.columns(2)
        try:
            word_payload = build_report_docx(general_context)
        except Exception:
            col_a.error("Word 报告暂时无法生成。")
        else:
            col_a.download_button(
                "下载通用报告 Word", data=word_payload,
                file_name=f"{safe_name}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                width="stretch", type="primary",
            )
        try:
            pdf_payload = build_report_pdf(general_context)
        except Exception:
            col_b.error("PDF 报告暂时无法生成；Word 下载不受影响。")
        else:
            col_b.download_button(
                "下载通用报告 PDF", data=pdf_payload,
                file_name=f"{safe_name}.pdf", mime="application/pdf",
                width="stretch", type="primary",
            )
        return

    st.subheader("企业决策报告")
    st.caption("只有公司评分和Action Plan都通过人工审核后，才会把企业资料与行业结论合并为决策版报告。")
    reasons = enterprise_report_gate_reasons(project)
    if reasons:
        st.warning("企业决策版尚未就绪：\n\n" + "\n\n".join(f"- {reason}" for reason in reasons))
        navigation = st.columns(2)
        if navigation[0].button("查看 Company Scorecard", width="stretch"):
            queue_page_navigation(st.session_state, "company_scorecard")
            st.rerun()
        if navigation[1].button("查看 Action Plan", width="stretch"):
            queue_page_navigation(st.session_state, "action_plan")
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

    st.success("企业决策报告已生成；内部追溯关系保留在审核工作台，不进入正式交付正文。")
    render_report_preview(
        enterprise_report.markdown,
        key=f"decision_enterprise_{project.project_id}",
        expanded=True,
        label="预览企业决策报告",
    )
    enterprise_context = project_report_context(
        project,
        title=enterprise_report.title,
        markdown=enterprise_report.markdown,
        report_status="经人工审核的企业战略决策报告",
        generated_at=enterprise_report.generated_at,
    )
    col_c, col_d = st.columns(2)
    try:
        word_payload = build_report_docx(enterprise_context)
    except Exception:
        col_c.error("Word 报告暂时无法生成。")
    else:
        col_c.download_button(
            "下载企业决策报告 Word",
            data=word_payload,
            file_name=f"{safe_name}.enterprise-decision.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch",
            type="primary",
        )
    try:
        pdf_payload = build_report_pdf(enterprise_context)
    except Exception:
        col_d.error("PDF 报告暂时无法生成；Word 下载不受影响。")
    else:
        col_d.download_button(
            "下载企业决策报告 PDF",
            data=pdf_payload,
            file_name=f"{safe_name}.enterprise-decision.pdf",
            mime="application/pdf",
            width="stretch",
            type="primary",
        )

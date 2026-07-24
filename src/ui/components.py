"""Reusable Streamlit presentation components."""

from __future__ import annotations

from html import escape

import streamlit as st

from src.models.research import MethodologyTrace
from src.state.project import ProjectState, ResearchMode, WorkflowStatus


MODE_LABELS = {
    ResearchMode.GENERAL: "General Research",
    ResearchMode.INDUSTRY_PACK: "Industry Pack",
    ResearchMode.GOLDEN_CASE: "案例展示",
    ResearchMode.DEMO_FALLBACK: "Demo Fallback",
}

STATUS_LABELS = {
    WorkflowStatus.NOT_STARTED: "Not Started",
    WorkflowStatus.READY: "Ready",
    WorkflowStatus.IN_PROGRESS: "In Progress",
    WorkflowStatus.NEEDS_REVIEW: "Needs Review",
    WorkflowStatus.COMPLETED: "Completed",
    WorkflowStatus.BLOCKED: "Blocked",
    WorkflowStatus.NOT_APPLICABLE: "Not Applicable",
}


def page_header(eyebrow: str, title: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="ia-page-head">
          <div class="ia-eyebrow">{escape(eyebrow)}</div>
          <h1>{escape(title)}</h1>
          <p>{escape(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(text: str, *, accent: bool = False) -> str:
    variant = " ia-badge-accent" if accent else ""
    return f'<span class="ia-badge{variant}">{escape(text)}</span>'


def render_project_strip(project: ProjectState | None) -> None:
    if project is None:
        st.markdown(
            badge("No active project") + badge("General Research Ready", accent=True),
            unsafe_allow_html=True,
        )
        return
    mode = MODE_LABELS[project.research_mode]
    pack = project.industry_pack or "No Industry Pack"
    st.markdown(
        badge(mode, accent=True)
        + badge(project.industry)
        + badge(project.region)
        + badge(pack),
        unsafe_allow_html=True,
    )


def information_card(title: str, copy: str, *, value: str | None = None) -> None:
    value_html = f'<div class="ia-stat">{escape(value)}</div>' if value else ""
    st.markdown(
        f"""
        <div class="ia-card">
          <div class="ia-card-title">{escape(title)}</div>
          <div class="ia-card-copy">{escape(copy)}</div>
          {value_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def require_project(project: ProjectState | None) -> bool:
    if project is not None:
        return True
    st.info("请先在 Project Home 创建一个通用行业研究项目，或加载案例展示。")
    return False


def workflow_status_text(status: WorkflowStatus) -> str:
    return STATUS_LABELS[status]


def render_methodology_trace(trace: MethodologyTrace) -> None:
    lock_label = "SOP Locked" if trace.locked else "SOP Advisory"
    st.markdown(
        badge(lock_label, accent=True)
        + badge(trace.sop_name)
        + badge(f"v{trace.sop_version}"),
        unsafe_allow_html=True,
    )
    with st.expander("查看方法论追溯记录"):
        st.caption(f"SOP ID: {trace.sop_id}")
        st.caption(f"Content hash: {trace.sop_hash[:16]}…")
        st.write("适用规则：" + "、".join(trace.rule_ids))
        if trace.compliance_checks:
            st.write("结构校验：")
            for check in trace.compliance_checks:
                st.write(f"- {check}")

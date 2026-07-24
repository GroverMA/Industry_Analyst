"""Single-source navigation definitions for the Streamlit shell."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

import streamlit as st

from src.state.project import ProjectState
from src.state.session import ACTIVE_PAGE_KEY, clear_project


@dataclass(frozen=True, slots=True)
class PageDefinition:
    key: str
    label: str
    short_label: str


PAGES = (
    PageDefinition("home", "Project Home", "项目首页"),
    PageDefinition("research_studio", "Research Studio", "研究主流程"),
    PageDefinition("research_brief", "Research Brief", "研究简报"),
    PageDefinition("workflow", "Research Workflow", "研究流程"),
    PageDefinition("enterprise_sensing", "Enterprise Sensing", "企业感知"),
    PageDefinition("evidence_analysis", "Evidence & Analysis", "证据与分析"),
    PageDefinition("trend_forecast", "Trend Forecast", "趋势预测"),
    PageDefinition("company_scorecard", "Company Scorecard", "公司评分"),
    PageDefinition("action_plan", "Action Plan", "行动计划"),
    PageDefinition("decision_report", "Decision Report", "决策报告"),
)


def render_sidebar(project: ProjectState | None) -> str:
    with st.sidebar:
        st.markdown(
            """
            <div class="ia-brand">
              <div class="ia-brand-name">Industry Analyst OS</div>
              <div class="ia-brand-sub">Evidence-first research workspace</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if project:
            st.markdown(
                f"""
                <div class="ia-sidebar-project">
                  <strong>{escape(project.project_name)}</strong><br/>
                  <span>{escape(project.industry)} · {escape(project.region)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="ia-sidebar-project">
                  <strong>尚未创建项目</strong><br/>
                  <span>从任意行业开始新的研究</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        labels = [f"{page.label}  ·  {page.short_label}" for page in PAGES]
        keys = [page.key for page in PAGES]
        current = st.session_state.get(ACTIVE_PAGE_KEY, "home")
        index = keys.index(current) if current in keys else 0
        selected_label = st.radio(
            "Research modules",
            labels,
            index=index,
            label_visibility="collapsed",
        )
        selected = PAGES[labels.index(selected_label)].key
        st.session_state[ACTIVE_PAGE_KEY] = selected

        st.divider()
        st.caption("Stage 7B · Strategy-to-Action Studio")
        if project and st.button("结束当前项目", width="stretch"):
            clear_project(st.session_state)
            st.rerun()
    return selected

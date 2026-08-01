"""First-entry role selector for the two Industry Analyst OS journeys."""

from __future__ import annotations

import streamlit as st

from src.state.user_role import ROLE_LABELS, ROLE_NOTES, UserRole, set_user_role


def render_role_selection() -> None:
    st.markdown(
        """
        <section class="ia-role-hero">
          <div class="ia-eyebrow">WELCOME TO INDUSTRY ANALYST OS</div>
          <h1>选择你的工作身份</h1>
          <p>系统将根据你的职责呈现最合适的研究路径。身份可随时切换，已有项目、研究进度和报告内容不会丢失。</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    consultant, reviewer = st.columns(2, gap="large")
    with consultant:
        with st.container(border=True):
            st.markdown("### Consultant · 咨询分析人员")
            st.caption("撰写报告的人")
            st.write("从问题定义、网页研究和人工审核开始，逐步形成行业报告与企业决策建议。")
            if st.button(
                "以研究顾问身份进入",
                type="primary",
                width="stretch",
                key="select_consultant_role",
            ):
                set_user_role(st.session_state, UserRole.CONSULTANT)
                st.rerun()
    with reviewer:
        with st.container(border=True):
            st.markdown("### Reviewer · 审阅人员")
            st.caption("审阅报告的人")
            st.write("确认研究范围后先查看完整报告，再检查引用来源、分析逻辑和决策依据。")
            if st.button(
                "以报告审阅者身份进入",
                type="primary",
                width="stretch",
                key="select_reviewer_role",
            ):
                set_user_role(st.session_state, UserRole.REVIEWER)
                st.rerun()
    st.caption(
        "进入后可在左侧栏随时切换身份。切换只改变工作台视图，不会重置研究。"
    )

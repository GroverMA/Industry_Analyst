"""First-entry selector for the two equivalent Trident research paths."""

from __future__ import annotations

import streamlit as st

from src.state.user_role import UserRole, set_user_role


def render_role_selection() -> None:
    st.markdown(
        """
        <section class="ia-role-hero">
          <div class="ia-eyebrow">CHOOSE YOUR RESEARCH PATH</div>
          <h1>选择你的研究方式</h1>
          <p>同一套专业研究标准，两种不同的工作路径。你可以随时切换，已有研究内容不会丢失。</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    consultant, reviewer = st.columns(2, gap="large")
    with consultant:
        with st.container(border=True, key="research_path_build"):
            st.markdown(
                """
                <div class="ia-path-en">Research Build First</div>
                <h3 class="ia-path-title">构建式研究</h3>
                <div class="ia-path-tag">从问题开始，分步骤与 AI 共同完成研究</div>
                <p class="ia-path-copy">从研究目标、市场范围和核心问题出发，逐步完成证据收集、分析验证、结论形成与行动建议。</p>
                <div class="ia-path-note"><strong>适合：</strong>适合希望参与研究过程，并在关键节点确认研究方向的用户。</div>
                <div class="ia-path-flow">定义问题 → 锁定边界 → 收集证据 → 分析验证 → 形成报告</div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "从问题开始",
                type="primary",
                width="stretch",
                key="select_consultant_role",
            ):
                set_user_role(st.session_state, UserRole.CONSULTANT)
                st.rerun()
    with reviewer:
        with st.container(border=True, key="research_path_review"):
            st.markdown(
                """
                <div class="ia-path-en">Report Review First</div>
                <h3 class="ia-path-title">审阅式研究</h3>
                <div class="ia-path-tag">从完整初稿开始审阅，检查和确认您关心的节点</div>
                <p class="ia-path-copy">确认研究范围后，由 AI 先完成报告初稿；你可以从结论出发，检查分析逻辑、引用来源、关键假设和决策依据。</p>
                <div class="ia-path-note"><strong>适合：</strong>适合希望快速了解全貌，再针对重点内容深入审阅的用户。</div>
                <div class="ia-path-flow">查看结论 → 检查逻辑 → 追溯证据 → 调整判断 → 确认报告</div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "生成报告初稿",
                type="primary",
                width="stretch",
                key="select_reviewer_role",
            ):
                set_user_role(st.session_state, UserRole.REVIEWER)
                st.rerun()
    st.markdown(
        '<p class="ia-path-footnote">两种方式使用相同的研究方法、证据标准与报告结构，区别仅在研究过程的呈现顺序。进入后可随时切换，不会重置研究内容。</p>',
        unsafe_allow_html=True,
    )

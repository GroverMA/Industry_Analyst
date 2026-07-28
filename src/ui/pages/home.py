"""Universal project creation and optional case demonstration entry."""

from __future__ import annotations

import streamlit as st

from src.state.golden_case import load_golden_case
from src.state.project import ProjectState, ResearchMode, WorkflowStatus
from src.state.session import ACTIVE_PAGE_KEY, set_project


def render(project: ProjectState | None) -> None:
    st.markdown(
        """
        <section class="ia-hero" style="padding:1.75rem 2rem;margin-bottom:1.15rem">
          <div class="ia-eyebrow">Universal Industry Research Agent</div>
          <h1 style="font-size:clamp(1.9rem,3vw,2.55rem)">Industry Analyst OS</h1>
          <p style="margin-top:.7rem">你的专属AI行业分析师：洞察未来趋势与竞争格局，发现市场机会，找到增长路径。</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if project:
        with st.container(border=True):
            st.subheader("当前研究项目")
            cols = st.columns([1.3, 1, 1])
            cols[0].write(f"**{project.project_name}**")
            cols[0].caption(f"{project.industry} · {project.region}")
            cols[1].metric("完成度", f"{project.completion_ratio:.0%}")
            cols[2].metric("当前步骤", project.current_step.replace("_", " ").title())
            if st.button("继续 Research Studio", type="primary"):
                st.session_state[ACTIVE_PAGE_KEY] = "research_studio"
                st.rerun()

    left, right = st.columns([1.5, 0.8], gap="large")
    with left:
        st.markdown(
            """
            <div style="margin:.15rem 0 .8rem">
              <span class="ia-badge ia-badge-accent">需要填写</span>
              <h2 style="font-size:1.45rem;margin:.65rem 0 .25rem">开始新的行业研究</h2>
              <p style="margin:0;font-size:.88rem">输入本次研究需要回答的问题。适用于任意行业、地区和公司。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        company_strategy_enabled = st.toggle(
            "启用企业战略路径（Company Scorecard + Action Plan）",
            value=False,
            help="关闭时仍可完成通用行业研究与趋势报告；开启后必须提供目标企业、战略意图和经确认的企业一手资料。",
            key="new_project_company_strategy_enabled",
        )
        if company_strategy_enabled:
            st.info(
                "企业战略路径已启用：Action Plan将以企业战略意图为首要约束。"
                "创建项目后，还需在Enterprise Sensing中确认至少一条脱敏企业资料。"
            )
        with st.form("new_research_project", border=True):
            project_name = st.text_input(
                "项目名称",
                placeholder="例如：全球工业机器人竞争格局研究",
            )
            col_a, col_b = st.columns(2)
            industry = col_a.text_input("行业", placeholder="例如：工业机器人")
            region = col_b.text_input("国家或地区", placeholder="例如：全球")
            st.markdown(
                """
                <div class="ia-prompt-guide">
                  <div class="ia-prompt-kicker">主要 Prompt · 必填</div>
                  <div class="ia-prompt-title">告诉 AI 这次研究最需要回答什么</div>
                  <div class="ia-prompt-copy">可以写行业现状、竞争格局、市场驱动、商业模式、客户需求、未来趋势，或希望重点验证的假设。</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            research_objective = st.text_area(
                "核心研究目标（必填）",
                placeholder="例如：系统研究全球工业机器人行业的市场现状、主要竞争者、增长驱动因素、商业模式变化与未来三年趋势。",
                height=150,
                help="这是Agent理解任务的主要输入。请尽量写清希望研究和回答的问题。",
            )
            target_company = ""
            company_strategy_objective = ""
            if company_strategy_enabled:
                st.markdown("#### 企业定制基础信息")
                target_company = st.text_input(
                    "目标企业（必填）",
                    placeholder="例如：某医疗科技公司（公开演示请使用虚构或脱敏名称）",
                )
                company_strategy_objective = st.text_area(
                    "企业战略意图（必填）",
                    placeholder=(
                        "例如：在保持核心业务现金流稳定的前提下，未来三年进入高增长细分市场，"
                        "并优先建立可复制的渠道和服务能力。"
                    ),
                    height=110,
                    help="这是Action Plan的首要输入。系统不会根据行业趋势替企业虚构战略。",
                )
            decision_context = st.text_area(
                "需要支持的业务决策（可选）",
                placeholder="例如：是否进入某个市场、优先投资哪条产品线。仅做行业全景研究时可以留空。",
                height=90,
            )
            col_c, col_d = st.columns(2)
            time_horizon = col_c.text_input("时间范围", placeholder="例如：2026—2030")
            output_language = col_d.selectbox(
                "输出语言", ["简体中文", "English", "中英双语"]
            )
            button_label = (
                "创建企业战略研究项目"
                if company_strategy_enabled
                else "创建通用研究项目"
            )
            submitted = st.form_submit_button(button_label, type="primary", width="stretch")
            if submitted:
                required = {
                    "项目名称": project_name,
                    "行业": industry,
                    "国家或地区": region,
                    "研究目标": research_objective,
                    "时间范围": time_horizon,
                }
                missing = [label for label, value in required.items() if not value.strip()]
                if company_strategy_enabled and not target_company.strip():
                    missing.append("目标企业")
                if company_strategy_enabled and not company_strategy_objective.strip():
                    missing.append("企业战略意图")
                if missing:
                    st.error("请补充：" + "、".join(missing))
                else:
                    new_project = ProjectState(
                        project_name=project_name,
                        industry=industry,
                        region=region,
                        target_company=target_company,
                        company_strategy_enabled=company_strategy_enabled,
                        company_strategy_objective=company_strategy_objective or None,
                        decision_context=decision_context or None,
                        research_objective=research_objective,
                        time_horizon=time_horizon,
                        output_language=output_language,
                        research_mode=ResearchMode.GENERAL,
                    )
                    if not company_strategy_enabled:
                        statuses = dict(new_project.workflow_status)
                        statuses["company_assessment"] = WorkflowStatus.NOT_APPLICABLE
                        statuses["action_plan"] = WorkflowStatus.NOT_APPLICABLE
                        new_project = new_project.model_copy(
                            update={"workflow_status": statuses}
                        )
                    set_project(st.session_state, new_project)
                    st.session_state[ACTIVE_PAGE_KEY] = "research_studio"
                    st.rerun()

    with right:
        st.markdown(
            """
            <div style="margin:.15rem 0 .8rem">
              <span class="ia-badge">仅供浏览</span>
              <h2 style="font-size:1.45rem;margin:.65rem 0 .25rem">产品介绍与案例</h2>
              <p style="margin:0;font-size:.88rem">了解产品能力或加载演示案例，此区域无需填写。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            st.markdown("#### 案例展示 · 中国分子诊断行业")
            st.caption("Industry Pack Enabled · 高精度研究案例")
            st.write(
                "模拟一家中国IVD企业在PCR、数字PCR、NGS和一体化方案之间进行资源配置。"
            )
            st.write("**作用：**证明研究深度，不限制通用行业能力。")
            if st.button("加载案例展示", width="stretch"):
                set_project(st.session_state, load_golden_case())
                st.session_state[ACTIVE_PAGE_KEY] = "research_studio"
                st.rerun()

        with st.container(border=True):
            st.markdown("#### 产品优势")
            st.markdown(
                """
                <div class="ia-status-row">
                  <div><strong>通用行业底座</strong><br><span class="ia-muted">任意行业均可研究，并可接入行业知识包。</span></div>
                </div>
                <div class="ia-status-row">
                  <div><strong>证据优先</strong><br><span class="ia-muted">重要结论连接原始来源，识别冲突与缺口。</span></div>
                </div>
                <div class="ia-status-row">
                  <div><strong>人工审核</strong><br><span class="ia-muted">市场口径、证据与报告内容均由用户确认。</span></div>
                </div>
                <div class="ia-status-row">
                  <div><strong>决策输出</strong><br><span class="ia-muted">行业洞察进一步映射至公司评分与行动计划。</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

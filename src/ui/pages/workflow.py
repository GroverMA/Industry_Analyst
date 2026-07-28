"""Visible research workflow and stage status."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st
from pydantic import ValidationError

from src.config import ConfigurationError
from src.providers.base import ProviderError
from src.services.research_planning import SOPComplianceError
from src.state.project import ProjectState, WORKFLOW_STEPS, WorkflowStatus
from src.state.session import queue_page_navigation, set_project
from src.ui.agent_services import research_planning_service
from src.ui.components import (
    page_header,
    render_methodology_trace,
    require_project,
    workflow_status_text,
)


def render(project: ProjectState | None) -> None:
    page_header(
        "02 · Research Workflow",
        "查看、确认与推进研究步骤",
        "研究能力不是一次性生成答案，而是由问题定义、任务拆解、证据、反证、判断和人工审核组成的可见流程。",
    )
    if not require_project(project):
        return
    assert project is not None

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("研究步骤", len(WORKFLOW_STEPS))
    col_b.metric("已完成", sum(s == WorkflowStatus.COMPLETED for s in project.workflow_status.values()))
    col_c.metric("整体完成度", f"{project.completion_ratio:.0%}")
    st.progress(project.completion_ratio)

    for index in range(0, len(WORKFLOW_STEPS), 2):
        columns = st.columns(2, gap="medium")
        for column, item in zip(columns, WORKFLOW_STEPS[index : index + 2]):
            key, title, description = item
            status = project.workflow_status[key]
            with column:
                with st.container(border=True):
                    st.caption(f"STEP {index + columns.index(column) + 1:02d}")
                    st.markdown(f"#### {title}")
                    st.write(description)
                    st.markdown(f"**{workflow_status_text(status)}**")

    st.divider()
    st.subheader("Research Planner")
    brief = project.research_brief_artifact
    if brief is None:
        st.warning("请先生成并确认AI Research Brief，再制定研究计划。")
        if st.button("返回 Research Brief"):
            queue_page_navigation(st.session_state, "research_brief")
            st.rerun()
        return
    if not brief.human_confirmed:
        st.warning("Research Brief正在等待人工确认。未经确认不能生成研究计划。")
        if st.button("前往确认 Research Brief"):
            queue_page_navigation(st.session_state, "research_brief")
            st.rerun()
        return

    with st.container(border=True):
        st.markdown("#### 已确认的研究定义")
        st.write(brief.decision_statement)
        st.caption(
            f"{brief.market_definition.core_market} · "
            f"{brief.market_definition.geography_scope} · "
            f"{brief.market_definition.time_scope}"
        )

    plan = project.research_plan_artifact
    generate_label = "重新生成研究计划" if plan else "AI 生成研究计划"
    if st.button(generate_label, type="primary", width="stretch"):
        try:
            with st.spinner("正在按照锁定SOP拆解任务、证据要求与人工校验节点…"):
                generated = research_planning_service().generate_plan(project, brief)
        except (ConfigurationError, ProviderError, SOPComplianceError, ValidationError) as exc:
            st.error(f"Research Plan生成失败：{exc}")
        else:
            statuses = dict(project.workflow_status)
            statuses["research_planning"] = WorkflowStatus.NEEDS_REVIEW
            statuses["evidence_collection"] = WorkflowStatus.NOT_STARTED
            updated = project.model_copy(
                update={
                    "research_plan_artifact": generated,
                    "evidence_collection_artifact": None,
                    "industry_analysis_artifact": None,
                    "future_intelligence_artifact": None,
                    "general_report_artifact": None,
                    "workflow_status": statuses,
                    "current_step": "research_planning",
                    "updated_at": datetime.now(UTC),
                }
            )
            set_project(st.session_state, updated)
            st.rerun()

    if plan is None:
        st.info("点击“AI 生成研究计划”，系统会真实调用HKGAI Modelhub。此时仍不会搜索网页。")
        return

    render_methodology_trace(plan.methodology)
    st.write(plan.plan_summary)
    st.markdown("#### 研究任务")
    for task in plan.tasks:
        with st.expander(f"{task.task_id} · {task.title}"):
            st.write(task.objective)
            st.markdown("**研究问题**")
            for question in task.questions:
                st.write(f"- {question}")
            st.markdown("**需要的信息与优先来源**")
            st.write("信息：" + "；".join(task.information_needs))
            st.write("来源：" + "；".join(task.preferred_sources))
            st.markdown("**预设搜索式**")
            for query in task.search_queries:
                st.code(query, language=None)
            st.markdown("**证据与校验**")
            st.write(task.evidence_standard)
            st.write("反证要求：是" if task.counter_evidence_required else "反证要求：否")
            st.write("人工校验：" + task.validation_gate)
            if task.depends_on:
                st.caption("依赖任务：" + "、".join(task.depends_on))

    col_d, col_e = st.columns(2)
    col_d.metric("研究任务", len(plan.tasks))
    col_e.metric("人工审核关卡", len(plan.human_review_gates))
    with st.container(border=True):
        st.markdown("#### Human Review Gates")
        for gate in plan.human_review_gates:
            st.write(f"- {gate}")
        if plan.unresolved_gaps:
            st.markdown("**尚未解决的信息缺口**")
            for gap in plan.unresolved_gaps:
                st.write(f"- {gap}")

    if plan.human_confirmed:
        st.success("研究计划已经人工批准，可以进入Evidence Collection。")
    elif st.button("批准研究计划并进入证据搜索", type="primary", width="stretch"):
        approved_payload = plan.model_dump()
        approved_payload["human_confirmed"] = True
        approved = type(plan).model_validate(approved_payload)
        statuses = dict(project.workflow_status)
        statuses["research_planning"] = WorkflowStatus.COMPLETED
        statuses["evidence_collection"] = WorkflowStatus.READY
        updated = project.model_copy(
            update={
                "research_plan_artifact": approved,
                "workflow_status": statuses,
                "current_step": "evidence_collection",
                "updated_at": datetime.now(UTC),
            }
        )
        set_project(st.session_state, updated)
        st.rerun()

"""SOP-governed Research Brief generation, editing, and approval."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st
from pydantic import ValidationError

from src.config import ConfigurationError
from src.knowledge.sop import load_active_sop
from src.models.research import ResearchBriefArtifact
from src.providers.base import ProviderError
from src.services.research_planning import SOPComplianceError
from src.state.project import ProjectState, WorkflowStatus
from src.state.session import queue_page_navigation, set_project
from src.ui.agent_services import research_planning_service
from src.ui.components import (
    badge,
    page_header,
    render_methodology_trace,
    require_project,
)


def _to_lines(values: list[str]) -> str:
    return "\n".join(values)


def _from_lines(value: str) -> list[str]:
    return [line.strip(" -\t") for line in value.splitlines() if line.strip(" -\t")]


def _replace_project_inputs(project: ProjectState, values: dict[str, object]) -> ProjectState:
    payload = project.model_dump()
    payload.update(values)
    payload["updated_at"] = datetime.now(UTC)
    return ProjectState.model_validate(payload)


def render(project: ProjectState | None) -> None:
    page_header(
        "01 · Research Brief",
        "先定义问题，再开始研究",
        "AI按照当前锁定的Research SOP澄清决策、市场边界、假设和信息缺口；用户确认后才能生成研究计划。",
    )
    if not require_project(project):
        return
    assert project is not None

    sop = load_active_sop()
    st.markdown(
        badge("SOP Locked", accent=True)
        + badge(sop.display_name)
        + badge(f"v{sop.version}"),
        unsafe_allow_html=True,
    )
    if sop.pack_type == "baseline":
        st.warning("当前使用通用研究方法基线；更新后的专业方法包可通过版本化配置接入。")

    st.subheader("A. 项目原始输入")
    company_strategy_enabled = st.toggle(
        "企业战略决策支持",
        value=project.company_strategy_enabled,
        key=f"brief_strategy_path_{project.project_id}",
        help="通用行业报告无需启用。启用后，目标企业、战略意图和经确认的一手资料是公司评分与Action Plan的硬性条件。",
    )
    if company_strategy_enabled:
        st.info("Action Plan只服务于下方明确填写的企业战略意图，不会由AI自行创造战略目标。")
    with st.form("edit_research_inputs", border=True):
        col_a, col_b = st.columns(2)
        project_name = col_a.text_input("项目名称", value=project.project_name)
        industry = col_b.text_input("行业", value=project.industry)
        col_c, col_d = st.columns(2)
        region = col_c.text_input("国家或地区", value=project.region)
        time_horizon = col_d.text_input("时间范围", value=project.time_horizon)
        st.markdown(
            """
            <div class="ia-prompt-guide ia-prompt-guide-compact">
              <div class="ia-prompt-kicker">主要 Prompt · 必填</div>
              <div class="ia-prompt-title">核心研究目标</div>
              <div class="ia-prompt-copy">这是AI定义市场边界、研究问题和信息缺口的主要依据。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        research_objective = st.text_area(
            "核心研究目标（必填）", value=project.research_objective, height=130
        )
        target_company = st.text_input(
            "目标企业（企业战略路径必填）" if company_strategy_enabled else "目标企业（可选）",
            value=project.target_company or "",
        )
        company_strategy_objective = st.text_area(
            "企业战略意图（企业战略路径必填）",
            value=project.company_strategy_objective or "",
            placeholder=(
                "说明企业希望到达的战略位置、必须守住的边界、资源或风险约束。"
                if company_strategy_enabled
                else "通用行业研究可以留空。"
            ),
            height=110,
            help="后续Action Plan必须逐项说明与该战略意图的关系。",
        )
        output_language = st.selectbox(
            "输出语言",
            ["简体中文", "English", "中英双语"],
            index=["简体中文", "English", "中英双语"].index(project.output_language),
        )
        save_inputs = st.form_submit_button("保存项目输入", width="stretch")
        if save_inputs:
            strategy_changed = (
                company_strategy_enabled != project.company_strategy_enabled
                or (target_company.strip() or None) != project.target_company
                or (company_strategy_objective.strip() or None)
                != project.company_strategy_objective
            )
            try:
                updated = _replace_project_inputs(
                    project,
                    {
                        "project_name": project_name,
                        "industry": industry,
                        "region": region,
                        "time_horizon": time_horizon,
                        "target_company": target_company or None,
                        "company_strategy_enabled": company_strategy_enabled,
                        "company_strategy_objective": company_strategy_objective or None,
                        "decision_context": None,
                        "research_objective": research_objective,
                        "output_language": output_language,
                        "research_brief_artifact": None,
                        "research_plan_artifact": None,
                        "evidence_collection_artifact": None,
                        "industry_analysis_artifact": None,
                        "future_intelligence_artifact": None,
                        "general_report_artifact": None,
                        "market_scope_confirmed_at": None,
                        "last_pipeline_error": None,
                        "enterprise_sensing_artifact": (
                            None
                            if strategy_changed
                            else project.enterprise_sensing_artifact
                        ),
                    },
                )
            except ValidationError:
                st.error(
                    "请补充必填信息。企业战略路径开启时，目标企业和企业战略意图也必须填写。"
                )
            else:
                statuses = dict(updated.workflow_status)
                statuses["research_brief"] = WorkflowStatus.READY
                for step in (
                    "research_planning",
                    "evidence_collection",
                    "evidence_qa",
                    "industry_analysis",
                    "future_intelligence",
                    "human_review",
                    "decision_report",
                ):
                    statuses[step] = WorkflowStatus.NOT_STARTED
                statuses["company_assessment"] = (
                    WorkflowStatus.NOT_STARTED
                    if company_strategy_enabled
                    else WorkflowStatus.NOT_APPLICABLE
                )
                statuses["action_plan"] = (
                    WorkflowStatus.NOT_STARTED
                    if company_strategy_enabled
                    else WorkflowStatus.NOT_APPLICABLE
                )
                updated = updated.model_copy(update={"workflow_status": statuses})
                set_project(st.session_state, updated)
                st.rerun()

    st.subheader("B. AI Research Brief")
    st.caption("这一步会真实调用HKGAI Modelhub，但不会搜索网页，也不会生成未经证据支持的市场结论。")
    generate_label = "重新生成研究定义" if project.research_brief_artifact else "AI 生成研究定义"
    if st.button(generate_label, type="primary", width="stretch"):
        try:
            with st.spinner("正在按照锁定SOP定义研究问题与市场边界…"):
                artifact = research_planning_service().generate_brief(project)
        except (ConfigurationError, ProviderError, SOPComplianceError, ValidationError) as exc:
            st.error(f"Research Brief生成失败：{exc}")
        else:
            statuses = dict(project.workflow_status)
            statuses["research_brief"] = WorkflowStatus.NEEDS_REVIEW
            statuses["research_planning"] = WorkflowStatus.NOT_STARTED
            updated = project.model_copy(
                update={
                    "research_brief_artifact": artifact,
                    "research_plan_artifact": None,
                    "evidence_collection_artifact": None,
                    "industry_analysis_artifact": None,
                    "future_intelligence_artifact": None,
                    "general_report_artifact": None,
                    "workflow_status": statuses,
                    "current_step": "research_brief",
                    "updated_at": datetime.now(UTC),
                }
            )
            set_project(st.session_state, updated)
            st.rerun()

    artifact = project.research_brief_artifact
    if artifact is None:
        st.info("尚未生成Research Brief。保存上方输入后，点击“AI 生成研究定义”。")
        return

    render_methodology_trace(artifact.methodology)
    with st.form("review_research_brief", border=True):
        st.markdown("#### 原始Prompt与AI理解")
        st.caption(project.research_objective)
        decision_statement = st.text_area(
            "AI理解后的研究目标", value=artifact.decision_statement, height=90
        )
        st.markdown("#### 市场边界")
        market = artifact.market_definition
        core_market = st.text_input("核心市场定义", value=market.core_market)
        col_e, col_f = st.columns(2)
        product_scope = col_e.text_area("产品/服务范围", value=market.product_scope)
        customer_scope = col_f.text_area("客户范围", value=market.customer_scope)
        col_g, col_h = st.columns(2)
        geography_scope = col_g.text_input("地域范围", value=market.geography_scope)
        time_scope = col_h.text_input("时间范围", value=market.time_scope)
        value_chain_scope = st.text_area("价值链范围", value=market.value_chain_scope)
        market_sizing_basis = st.text_area(
            "市场规模统计口径", value=market.market_sizing_basis
        )
        competitor_definition = st.text_area(
            "竞争者与可比公司识别口径", value=market.competitor_definition
        )
        col_i, col_j = st.columns(2)
        inclusions = col_i.text_area("包含项（每行一项）", value=_to_lines(market.inclusions))
        exclusions = col_j.text_area("排除项（每行一项）", value=_to_lines(market.exclusions))
        adjacent_markets = st.text_area(
            "相邻市场（每行一项）", value=_to_lines(market.adjacent_markets)
        )
        key_questions = st.text_area(
            "关键研究问题（每行一项）", value=_to_lines(artifact.key_questions), height=170
        )
        information_gaps = st.text_area(
            "信息缺口（每行一项）", value=_to_lines(artifact.information_gaps), height=120
        )
        hypotheses = st.text_area(
            "初步假设（每行一项）", value=_to_lines(artifact.hypotheses), height=120
        )
        clarification_questions = st.text_area(
            "需要用户澄清的问题（每行一项）",
            value=_to_lines(artifact.clarification_questions),
            height=120,
        )
        confidence_note = st.text_area("当前置信度说明", value=artifact.confidence_note)
        col_k, col_l = st.columns(2)
        save_brief = col_k.form_submit_button("保存修改", width="stretch")
        confirm_brief = col_l.form_submit_button(
            "确认并进入 Research Workflow", type="primary", width="stretch"
        )

        if save_brief or confirm_brief:
            brief_payload = artifact.model_dump()
            brief_payload.update(
                {
                    "decision_statement": decision_statement,
                    "original_prompt": project.research_objective,
                    "interpreted_intent": artifact.interpreted_intent.model_copy(
                        update={
                            "interpreted_objective": decision_statement,
                            "must_answer_questions": _from_lines(key_questions),
                        }
                    ),
                    "market_definition": {
                        "core_market": core_market,
                        "product_scope": product_scope,
                        "customer_scope": customer_scope,
                        "geography_scope": geography_scope,
                        "value_chain_scope": value_chain_scope,
                        "time_scope": time_scope,
                        "inclusions": _from_lines(inclusions),
                        "exclusions": _from_lines(exclusions),
                        "market_sizing_basis": market_sizing_basis,
                        "competitor_definition": competitor_definition,
                        "adjacent_markets": _from_lines(adjacent_markets),
                        "ambiguities": market.ambiguities,
                    },
                    "key_questions": _from_lines(key_questions),
                    "information_gaps": _from_lines(information_gaps),
                    "hypotheses": _from_lines(hypotheses),
                    "clarification_questions": _from_lines(clarification_questions),
                    "confidence_note": confidence_note,
                    "human_confirmed": confirm_brief,
                    "confirmed_at": datetime.now(UTC) if confirm_brief else None,
                }
            )
            try:
                reviewed = ResearchBriefArtifact.model_validate(brief_payload)
            except ValidationError as exc:
                st.error(f"请补充完整的Research Brief：{exc.errors()[0]['msg']}")
            else:
                statuses = dict(project.workflow_status)
                statuses["research_brief"] = (
                    WorkflowStatus.COMPLETED if confirm_brief else WorkflowStatus.NEEDS_REVIEW
                )
                statuses["research_planning"] = (
                    WorkflowStatus.READY if confirm_brief else WorkflowStatus.NOT_STARTED
                )
                updated = project.model_copy(
                    update={
                        "research_brief_artifact": reviewed,
                        "workflow_status": statuses,
                        "current_step": "research_planning" if confirm_brief else "research_brief",
                        "market_scope_confirmed_at": (
                            datetime.now(UTC) if confirm_brief else None
                        ),
                        "updated_at": datetime.now(UTC),
                    }
                )
                set_project(st.session_state, updated)
                if confirm_brief:
                    queue_page_navigation(st.session_state, "workflow")
                    st.rerun()

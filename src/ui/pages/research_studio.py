"""Single-page, resumable research pipeline with three shared human gates."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import streamlit as st
from pydantic import ValidationError

from src.config import ConfigurationError
from src.models.analysis import AnalysisReviewStatus
from src.models.enterprise import (
    EnterpriseEvidenceCategory,
    EnterpriseEvidenceItem,
    EnterpriseReviewStatus,
    EnterpriseSensitivity,
    EnterpriseStatementType,
)
from src.models.evidence import EvidenceCollectionArtifact, EvidenceReviewStatus
from src.models.future import ForecastReviewStatus, ScenarioType
from src.models.revision import RevisionTarget
from src.models.research import MarketDefinition, ResearchBriefArtifact, ResearchIntent
from src.providers.base import ProviderError
from src.services.evidence_collection import (
    MIN_GATE_ONE_QA,
    MIN_PROMPT_RELEVANCE,
    EvidenceCollectionError,
    evidence_coverage_advisories,
    evidence_coverage_gaps,
    evidence_gate_reasons,
    evidence_is_gate_one_candidate,
    review_evidence,
    unresolved_task_run,
    upsert_task_run,
)
from src.services.future_intelligence import (
    FutureIntelligenceError,
    forecast_gate_reasons,
    review_forecast_item,
)
from src.services.industry_analysis import (
    IndustryAnalysisError,
    analysis_gate_reasons,
    review_analysis_finding,
)
from src.services.enterprise_sensing import (
    company_strategy_gate_reasons,
    diagnosis_title_from_symptoms,
    upsert_enterprise_entry,
)
from src.services.company_assessment import company_scorecard_eligibility
from src.services.report_generation import (
    ReportGenerationError,
    market_sizing_calculation_rows,
)
from src.services.report_export import (
    build_report_docx,
    build_report_pdf,
    project_report_context,
)
from src.services.research_planning import SOPComplianceError
from src.services.reviewer_orchestration import ReviewerPipelineError
from src.services.reviewer_revision import (
    ReviewerRevisionError,
    finalize_revision,
    initialize_revision,
    reviewer_attention_points,
    save_report_version,
)
from src.state.project import (
    ProjectState,
    WorkflowStatus,
    WorkspaceMode,
    rewind_to_previous_review_gate,
)
from src.state.session import queue_page_navigation, set_project
from src.state.user_role import UserRole, get_user_role
from src.ui.agent_services import (
    evidence_collection_service,
    future_intelligence_service,
    industry_analysis_service,
    report_generation_service,
    reviewer_orchestration_service,
    reviewer_revision_service,
    research_planning_service,
)
from src.ui.components import badge, information_card, page_header, require_project
from src.ui.report_preview import render_report_preview
from src.ui.scorecard_visuals import render_scorecard_radar


MODE_LABELS = {
    WorkspaceMode.QUICK_REPORT: "快速通用报告",
    WorkspaceMode.ANALYST_WORKSPACE: "高级分析师工作台",
}


def _save(project: ProjectState) -> None:
    set_project(st.session_state, project)


def _strategy_output_reset() -> dict:
    """Invalidate company recommendations whenever their upstream evidence changes."""

    return {
        "company_scorecard_artifact": None,
        "action_plan_artifact": None,
        "enterprise_decision_report_artifact": None,
        "content_revision_artifact": None,
    }


def _reset_strategy_statuses(
    statuses: dict[str, WorkflowStatus],
    *,
    enabled: bool,
) -> dict[str, WorkflowStatus]:
    updated = dict(statuses)
    reset_value = WorkflowStatus.NOT_STARTED if enabled else WorkflowStatus.NOT_APPLICABLE
    updated["company_assessment"] = reset_value
    updated["action_plan"] = reset_value
    updated["decision_report"] = WorkflowStatus.NOT_STARTED
    return updated


def _records(value) -> list[dict]:
    if hasattr(value, "to_dict"):
        return value.to_dict("records")
    return list(value)


def _recommended_evidence_ids(
    artifact: EvidenceCollectionArtifact,
    plan,
) -> set[str]:
    """Return a minimum sufficient, quality-qualified evidence set.

    The greedy set-cover favors evidence that answers the largest number of
    still-uncovered task and original-Prompt questions, then favors independent
    domains, relevance and quality. Weak evidence is never selected to create
    a false impression of coverage.
    """

    task_map = {task.task_id: task for task in plan.tasks}
    required: set[str] = set()
    for task in plan.tasks:
        required.update(
            f"TASK:{task.task_id}-Q{index}"
            for index in range(1, len(task.questions) + 1)
        )
        required.update(f"PROMPT:{item}" for item in task.prompt_question_ids)

    def coverage(item) -> set[str]:
        task = task_map.get(item.task_id)
        if task is None:
            return set()
        task_ids = item.question_ids or [
            f"{task.task_id}-Q{index}"
            for index in range(1, len(task.questions) + 1)
        ]
        prompt_ids = item.prompt_question_ids or task.prompt_question_ids
        return {
            *(f"TASK:{question_id}" for question_id in task_ids),
            *(f"PROMPT:{question_id}" for question_id in prompt_ids),
        }

    eligible = [
        item for item in artifact.evidence if evidence_is_gate_one_candidate(item)
    ]
    source_map = {source.source_id: source for source in artifact.sources}
    selected: set[str] = set()
    selected_domains: set[str] = set()
    remaining = set(required)
    while remaining:
        ranked = []
        for item in eligible:
            if item.evidence_id in selected:
                continue
            newly_covered = coverage(item) & remaining
            if not newly_covered:
                continue
            source = source_map.get(item.source_id)
            domain = source.domain if source is not None else item.source_id
            ranked.append(
                (
                    len(newly_covered),
                    int(domain not in selected_domains),
                    item.prompt_relevance,
                    item.qa_score,
                    item,
                    domain,
                )
            )
        if not ranked:
            break
        *_, chosen, domain = max(ranked, key=lambda value: value[:4])
        selected.add(chosen.evidence_id)
        selected_domains.add(domain)
        remaining -= coverage(chosen)
    return selected


def _to_lines(values: list[str]) -> str:
    return "\n".join(values)


def _from_lines(value: str) -> list[str]:
    return [line.strip(" -\t") for line in value.splitlines() if line.strip(" -\t")]


def _generate_research_brief(project: ProjectState) -> None:
    try:
        with st.spinner("AI正在理解原始Prompt，并形成可审阅的市场描述与研究口径…"):
            brief = research_planning_service().generate_brief(project)
    except (ConfigurationError, ProviderError, SOPComplianceError, ValidationError) as exc:
        st.error(f"研究需求解析未完成：{exc}")
        return
    statuses = dict(project.workflow_status)
    statuses = _reset_strategy_statuses(statuses, enabled=project.company_strategy_enabled)
    statuses["research_brief"] = WorkflowStatus.NEEDS_REVIEW
    updated = project.model_copy(
        update={
            "research_brief_artifact": brief,
            "research_plan_artifact": None,
            "evidence_collection_artifact": None,
            "industry_analysis_artifact": None,
            "future_intelligence_artifact": None,
            "general_report_artifact": None,
            **_strategy_output_reset(),
            "market_scope_confirmed_at": None,
            "last_pipeline_error": None,
            "workflow_status": statuses,
            "current_step": "research_brief",
            "updated_at": datetime.now(UTC),
        }
    )
    _save(updated)
    st.rerun()


def _render_gate_zero(project: ProjectState, *, reviewer_mode: bool = False) -> None:
    brief = project.research_brief_artifact
    assert brief is not None
    st.subheader("Gate 0 · 对齐AI对研究问题和市场口径的理解")
    st.caption(
        "AI已经根据你的原始Prompt生成市场描述。请修改任何不准确的定义；确认后的版本将成为检索、分析、趋势和报告的共同口径。"
        "上方所有字段均可直接修改；待验证问题请在右侧填写你的确认口径或补充判断。"
    )
    with st.container(border=True):
        st.markdown("#### 用户原始Prompt")
        st.write(project.research_objective)
        intent = brief.interpreted_intent
        if intent.terminology_map:
            st.markdown("**AI术语理解**")
            for term, meaning in intent.terminology_map.items():
                st.write(f"- {term} → {meaning}")

    market = brief.market_definition
    with st.form("studio_gate_zero_form", border=True):
        interpreted_objective = st.text_area(
            "AI理解后的研究目标",
            value=intent.interpreted_objective or brief.decision_statement,
            height=100,
        )
        must_answer = st.text_area(
            "最终报告必须回答的问题（每行一项）",
            value=_to_lines(intent.must_answer_questions or brief.key_questions),
            height=150,
        )
        st.markdown("#### 市场描述与统计口径")
        core_market = st.text_area("核心市场定义", value=market.core_market, height=90)
        col_a, col_b = st.columns(2)
        product_scope = col_a.text_area("产品/服务范围", value=market.product_scope)
        customer_scope = col_b.text_area("客户与应用范围", value=market.customer_scope)
        col_c, col_d = st.columns(2)
        geography_scope = col_c.text_input("地域范围", value=market.geography_scope)
        time_scope = col_d.text_input("时间范围", value=market.time_scope)
        value_chain_scope = st.text_area("价值链范围", value=market.value_chain_scope)
        market_sizing_basis = st.text_area(
            "市场规模统计口径",
            value=market.market_sizing_basis,
            help="例如终端采购额、企业收入、检测服务收入、销量或装机量。无法确认时明确写尚待验证。",
        )
        competitor_definition = st.text_area(
            "竞争者与可比公司识别口径",
            value=market.competitor_definition,
            help="明确直接竞争、间接替代、Benchmark和相邻市场的判断依据。",
        )
        col_e, col_f = st.columns(2)
        inclusions = col_e.text_area("纳入范围（每行一项）", value=_to_lines(market.inclusions))
        exclusions = col_f.text_area("排除范围（每行一项）", value=_to_lines(market.exclusions))
        adjacent_markets = st.text_area(
            "相邻但不属于核心市场的领域（每行一项）",
            value=_to_lines(market.adjacent_markets),
        )
        st.markdown("#### 仍需在研究中验证的口径问题")
        st.caption("左侧为AI识别的待验证问题，右侧为研究者的对应确认口径。问题和回答均可修改。")
        ambiguity_questions = list(dict.fromkeys([*intent.ambiguities, *market.ambiguities]))
        ambiguity_questions = ambiguity_questions or [""]
        # Projects kept alive across a Streamlit hot deployment may contain a
        # pre-migration ResearchBrief instance. Gate 0 must remain renderable
        # even if that legacy nested object lacks this newly introduced field.
        saved_clarification_responses = (
            getattr(brief, "clarification_responses", None) or {}
        )
        ambiguity_rows: list[tuple[str, str]] = []
        for index, question in enumerate(ambiguity_questions, start=1):
            question_col, response_col = st.columns(2)
            edited_question = question_col.text_area(
                f"待验证问题 {index}",
                value=question,
                key=f"studio_scope_question_{index}",
                height=92,
            )
            edited_response = response_col.text_area(
                f"研究者确认口径 {index}",
                value=saved_clarification_responses.get(question, ""),
                placeholder="请在此直接填写确认口径、取舍原则或需要采用的判断。",
                key=f"studio_scope_response_{index}",
                height=92,
            )
            ambiguity_rows.append((edited_question.strip(), edited_response.strip()))
        additional_ambiguities = st.text_area(
            "新增待验证问题（可选，每行一项）",
            value="",
            help="如需增加问题，可在此填写；确认后将进入研究口径清单。",
        )
        confirmed = st.checkbox(
            "我已核对并确认上述市场定义、纳入排除范围和报告必答问题",
            key="studio_gate_zero_confirmation",
        )
        submit = st.form_submit_button(
            (
                "确认研究范围并生成完整可审阅报告"
                if reviewer_mode
                else "确认Gate 0并开始网页研究"
            ),
            type="primary",
            width="stretch",
        )
    if not submit:
        return
    if not confirmed:
        st.error("请先勾选确认，表示你已经核对市场定义、纳入排除范围和报告必答问题。")
        return
    now = datetime.now(UTC)
    intent_payload = intent.model_dump()
    ambiguity_list = [question for question, _ in ambiguity_rows if question]
    ambiguity_list.extend(_from_lines(additional_ambiguities))
    ambiguity_list = list(dict.fromkeys(ambiguity_list))
    clarification_responses = {
        question: response
        for question, response in ambiguity_rows
        if question and response
    }
    intent_payload.update(
        {
            "interpreted_objective": interpreted_objective,
            "must_answer_questions": _from_lines(must_answer),
            "ambiguities": ambiguity_list,
        }
    )
    brief_payload = brief.model_dump()
    brief_payload.update(
        {
            "original_prompt": project.research_objective,
            "interpreted_intent": ResearchIntent.model_validate(intent_payload),
            "decision_statement": interpreted_objective,
            "key_questions": _from_lines(must_answer),
            "market_definition": MarketDefinition(
                core_market=core_market,
                product_scope=product_scope,
                customer_scope=customer_scope,
                geography_scope=geography_scope,
                value_chain_scope=value_chain_scope,
                time_scope=time_scope,
                inclusions=_from_lines(inclusions),
                exclusions=_from_lines(exclusions),
                market_sizing_basis=market_sizing_basis,
                competitor_definition=competitor_definition,
                adjacent_markets=_from_lines(adjacent_markets),
                ambiguities=ambiguity_list,
            ),
            "clarification_responses": clarification_responses,
            "human_confirmed": True,
            "confirmed_at": now,
        }
    )
    try:
        reviewed = ResearchBriefArtifact.model_validate(brief_payload)
    except ValidationError as exc:
        st.error(f"市场口径尚不完整：{exc.errors()[0]['msg']}")
        return
    statuses = dict(project.workflow_status)
    statuses["research_brief"] = WorkflowStatus.COMPLETED
    statuses["research_planning"] = WorkflowStatus.READY
    updated = project.model_copy(
        update={
            "research_brief_artifact": reviewed,
            "market_scope_confirmed_at": now,
            "workflow_status": statuses,
            "current_step": "research_planning",
            "updated_at": now,
        }
    )
    _save(updated)
    if reviewer_mode:
        _run_reviewer_report_pipeline(updated)
    else:
        _run_research_design_and_search(updated)


def _pipeline_flags(project: ProjectState) -> list[tuple[str, bool]]:
    plan = project.research_plan_artifact
    evidence = project.evidence_collection_artifact
    evidence_complete = bool(
        plan
        and evidence
        and evidence.research_plan_id == plan.artifact_id
        and {run.task_id for run in evidence.task_runs} >= {task.task_id for task in plan.tasks}
    )
    content_confirmed = bool(
        project.industry_analysis_artifact
        and project.industry_analysis_artifact.human_confirmed
        and project.future_intelligence_artifact
        and project.future_intelligence_artifact.human_confirmed
    )
    role = get_user_role(st.session_state) or UserRole.CONSULTANT
    if role == UserRole.REVIEWER:
        report_ready = bool(
            project.enterprise_decision_report_artifact
            if project.company_strategy_enabled
            else project.general_report_artifact
        )
        reviewer_flags = [
            ("Prompt Analysis", project.research_brief_artifact is not None),
            (
                "Gate 0 · Scope",
                bool(
                    project.research_brief_artifact
                    and project.research_brief_artifact.human_confirmed
                ),
            ),
            (
                "Enterprise Report" if project.company_strategy_enabled else "General Report",
                report_ready,
            ),
            (
                "Content Revision",
                bool(
                    project.content_revision_artifact
                    and project.content_revision_artifact.finalized
                ),
            ),
            ("Reference Check", bool(evidence and evidence.evidence)),
            ("Industry Analysis", project.industry_analysis_artifact is not None),
            ("Future Intelligence", project.future_intelligence_artifact is not None),
        ]
        if project.company_strategy_enabled:
            sensing = project.enterprise_sensing_artifact
            return [
                ("Enterprise Sensing", bool(sensing and sensing.human_confirmed)),
                *reviewer_flags,
                ("Company Scorecard", project.company_scorecard_artifact is not None),
                ("Action Plan", project.action_plan_artifact is not None),
            ]
        return reviewer_flags

    shared_flags = [
        ("Prompt Analysis", project.research_brief_artifact is not None),
        ("Gate 0 · Scope", bool(project.research_brief_artifact and project.research_brief_artifact.human_confirmed)),
        ("Web Research", evidence_complete),
        ("Gate 1 · Evidence", bool(evidence and evidence.human_confirmed)),
        ("Industry Analysis", project.industry_analysis_artifact is not None),
        ("Future Intelligence", project.future_intelligence_artifact is not None),
        ("Gate 2 · Content", content_confirmed),
    ]
    if project.company_strategy_enabled:
        sensing = project.enterprise_sensing_artifact
        return [
            ("Enterprise Sensing", bool(sensing and sensing.human_confirmed)),
            *shared_flags,
            ("Company Scorecard", bool(project.company_scorecard_artifact and project.company_scorecard_artifact.human_confirmed)),
            ("Action Plan", bool(project.action_plan_artifact and project.action_plan_artifact.human_confirmed)),
            ("Enterprise Report", project.enterprise_decision_report_artifact is not None),
        ]
    return [*shared_flags, ("General Report", project.general_report_artifact is not None)]


def _render_progress(project: ProjectState) -> None:
    flags = _pipeline_flags(project)
    completed = sum(done for _, done in flags)
    progress_percent = (
        100 * max(completed - 1, 0) / max(len(flags) - 1, 1)
    )
    steps: list[str] = []
    for index, (label, done) in enumerate(flags, start=1):
        state_class = " ia-pipeline-step-done" if done else ""
        steps.append(
            f'<div class="ia-pipeline-step{state_class}">'
            f"<strong>{label}</strong>"
            f"<span>{index}</span></div>"
        )
    st.markdown(
        f'<div class="ia-pipeline-scroll"><div class="ia-pipeline-track" '
        f'style="--ia-step-count:{len(flags)};--ia-progress-width:{progress_percent * 0.91:.1f}%">'
        + "".join(steps)
        + "</div></div>",
        unsafe_allow_html=True,
    )
    st.caption(f"研究进度：{completed}/{len(flags)} 个节点已完成")


def _clear_stale_review_widget_state() -> None:
    """Drop review-widget values that are invalid after a workflow rewind.

    Streamlit keeps widget values across reruns.  A review decision from the
    invalidated branch must not silently reappear when the user reaches that
    gate again.
    """

    prefixes = (
        "studio_gate_zero_",
        "studio_gate_one_",
        "studio_gate_two_",
    )
    for key in list(st.session_state):
        if str(key).startswith(prefixes):
            st.session_state.pop(key, None)


def _render_rewind_control(project: ProjectState) -> None:
    """Offer a safe return to the preceding human-review gate, when available."""

    rewind_result = rewind_to_previous_review_gate(project)
    if rewind_result is None:
        return

    _, impact = rewind_result
    st.markdown(
        '<div class="ia-rewind-guide">'
        '<strong>需要修改前序内容？</strong>'
        '<span>返回最近的人工审核节点后，已保存的前序资料会保留，'
        '该节点之后不再有效的分析、趋势或报告会被清除。</span>'
        f'<small>{impact}</small>'
        "</div>",
        unsafe_allow_html=True,
    )
    if st.button(
        "← 返回上一审核节点",
        key=f"studio_rewind_{project.project_id}_{project.current_step}",
        width="stretch",
        help="保留该审核节点之前的研究成果，清除之后的依赖产物。",
    ):
        rewound, message = rewind_result
        _clear_stale_review_widget_state()
        _save(rewound)
        st.session_state["studio_rewind_notice"] = message
        st.rerun()


def _render_advanced_context(project: ProjectState) -> None:
    st.markdown("### 高级分析师工作台 · 企业定制层")
    st.caption(
        "企业资料与战略意图先完成确认，再沿用同一Research Brief、Research Plan、Evidence Matrix和三道审核，最后进入Scorecard和Action Plan。"
    )
    with st.expander("统一 Research Brief 与 Research Plan", expanded=False):
        brief = project.research_brief_artifact
        plan = project.research_plan_artifact
        if brief is None:
            st.info("完成AI Prompt分析后，本区会显示与主流程完全相同的Research Brief。")
        else:
            st.write(f"**研究目的：** {brief.decision_statement}")
            st.write(f"**核心市场：** {brief.market_definition.core_market}")
            st.write("**必答问题：**")
            for question in brief.interpreted_intent.must_answer_questions or brief.key_questions:
                st.write(f"- {question}")
        if plan is not None:
            st.write(f"**Research Plan：** {plan.plan_summary}")
            st.caption(f"{len(plan.tasks)}项任务 · 与本页网页检索共用同一计划ID")

    with st.form("studio_enterprise_strategy", border=True):
        st.markdown("#### 企业目标与战略意图")
        st.markdown("**企业战略决策支持：已启用**")
        enabled = True
        target_company = st.text_input("目标企业", value=project.target_company or "")
        strategy = st.text_area(
            "企业战略意图",
            value=project.company_strategy_objective or "",
            placeholder="例如：未来三年进入高增长细分市场，同时保持核心业务现金流稳定。",
            height=100,
        )
        save_strategy = st.form_submit_button("保存企业目标并同步后续模块", width="stretch")
    if save_strategy:
        if enabled and (not target_company.strip() or not strategy.strip()):
            st.error("启用企业战略决策支持时，请填写目标企业和企业战略意图。")
        else:
            strategy_changed = (
                enabled != project.company_strategy_enabled
                or (target_company.strip() or None) != project.target_company
                or (strategy.strip() or None) != project.company_strategy_objective
            )
            statuses = dict(project.workflow_status)
            statuses["company_assessment"] = (
                WorkflowStatus.NOT_STARTED if enabled else WorkflowStatus.NOT_APPLICABLE
            )
            statuses["action_plan"] = (
                WorkflowStatus.NOT_STARTED if enabled else WorkflowStatus.NOT_APPLICABLE
            )
            statuses["decision_report"] = WorkflowStatus.NOT_STARTED
            updated = project.model_copy(
                update={
                    "company_strategy_enabled": enabled,
                    "target_company": target_company or None,
                    "company_strategy_objective": strategy or None,
                    "decision_context": None,
                    "industry_analysis_artifact": (
                        None if strategy_changed else project.industry_analysis_artifact
                    ),
                    "future_intelligence_artifact": (
                        None if strategy_changed else project.future_intelligence_artifact
                    ),
                    "general_report_artifact": (
                        None if strategy_changed else project.general_report_artifact
                    ),
                    "company_scorecard_artifact": (
                        None if strategy_changed else project.company_scorecard_artifact
                    ),
                    "action_plan_artifact": (
                        None if strategy_changed else project.action_plan_artifact
                    ),
                    "enterprise_decision_report_artifact": (
                        None if strategy_changed else project.enterprise_decision_report_artifact
                    ),
                    "workflow_status": statuses,
                    "updated_at": datetime.now(UTC),
                }
            )
            _save(updated)
            st.rerun()

    artifact = project.enterprise_sensing_artifact
    accepted = (
        sum(item.review_status == EnterpriseReviewStatus.ACCEPTED for item in artifact.entries)
        if artifact else 0
    )
    cols = st.columns(5)
    cols[0].metric("企业一手资料", len(artifact.entries) if artifact else 0)
    cols[1].metric("已接受资料", accepted)
    cols[2].metric("Enterprise Sensing", "已确认" if artifact and artifact.human_confirmed else "必填/待确认")
    cols[3].metric(
        "Company Scorecard",
        "已确认" if project.company_scorecard_artifact and project.company_scorecard_artifact.human_confirmed else "待完成",
    )
    cols[4].metric(
        "Action Plan",
        "已确认" if project.action_plan_artifact and project.action_plan_artifact.human_confirmed else "待完成",
    )
    with st.expander("快速提交一个企业自我诊断问题", expanded=False):
        st.caption(
            "提交企业已经观察到的表现、症状或问题；系统将其作为待验证管理假设。"
            "多层企业文件、敏感级别和逐条审核请进入完整Enterprise Sensing。"
        )
        with st.form("studio_enterprise_quick_entry", border=True):
            observation_content = st.text_area(
                "当前表现、症状或已观察到的问题",
                placeholder="例如：重点客户渗透率低于预期，现有渠道触达与转化效率偏低。",
                height=110,
            )
            observation_owner = st.text_input("提交部门／责任人", placeholder="例如：商业运营负责人")
            observation_relevance = st.text_area("为什么会影响企业战略意图", height=80)
            add_observation = st.form_submit_button("提交诊断假设", width="stretch")
        if add_observation:
            try:
                item = EnterpriseEvidenceItem(
                    title=diagnosis_title_from_symptoms(observation_content),
                    category=EnterpriseEvidenceCategory.SELF_DIAGNOSIS,
                    statement_type=EnterpriseStatementType.HYPOTHESIS,
                    content=observation_content,
                    source_owner=observation_owner,
                    strategic_relevance=observation_relevance,
                    sensitivity=EnterpriseSensitivity.REDACTED_DEMO,
                    input_method="self_diagnosis",
                )
            except ValidationError:
                st.error("请填写当前表现、来源角色和战略相关性。")
            else:
                updated_artifact = upsert_enterprise_entry(artifact, project, item)
                statuses = _reset_strategy_statuses(
                    project.workflow_status,
                    enabled=project.company_strategy_enabled,
                )
                updated = project.model_copy(
                    update={
                        "enterprise_sensing_artifact": updated_artifact,
                        **_strategy_output_reset(),
                        "workflow_status": statuses,
                        "updated_at": datetime.now(UTC),
                    }
                )
                _save(updated)
                st.rerun()
    nav_a, nav_b, nav_c = st.columns(3)
    if nav_a.button("接入或审核企业一手数据", width="stretch"):
        queue_page_navigation(st.session_state, "enterprise_sensing")
        st.rerun()
    if nav_b.button("查看 Company Scorecard 条件", width="stretch"):
        queue_page_navigation(st.session_state, "company_scorecard")
        st.rerun()
    if nav_c.button("查看 Action Plan 条件", width="stretch"):
        queue_page_navigation(st.session_state, "action_plan")
        st.rerun()

    if project.company_strategy_enabled:
        reasons = company_strategy_gate_reasons(project)
        if reasons:
            st.info("企业战略研究尚未开始：请先完成企业一手资料输入与确认。" + "；".join(reasons))
        else:
            st.success("企业目标与一手数据资格已通过；完成行业趋势审核后即可进入Company Scorecard。")
    else:
        st.info("请从首页创建企业战略研究项目，以启用企业资料、Scorecard和Action Plan流程。")


def _run_task(project: ProjectState, task_id: str, query: str | None = None):
    assert project.research_plan_artifact is not None
    return asyncio.run(
        evidence_collection_service().collect_task(
            project,
            project.research_plan_artifact,
            task_id,
            query_override=query,
        )
    )


def _run_research_design_and_search(project: ProjectState) -> None:
    now = datetime.now(UTC)
    statuses = _reset_strategy_statuses(
        project.workflow_status,
        enabled=project.company_strategy_enabled,
    )
    current = project.model_copy(
        update={
            "execution_authorized_at": project.execution_authorized_at or now,
            "general_report_artifact": None,
            **_strategy_output_reset(),
            "workflow_status": statuses,
            "updated_at": now,
        }
    )
    planning = research_planning_service()
    progress = st.progress(0, text="正在根据已确认市场口径拆解研究任务…")
    try:
        brief = current.research_brief_artifact
        if brief is None or not brief.human_confirmed:
            raise SOPComplianceError("请先完成Gate 0市场口径对齐")
        progress.progress(0.15, text="正在拆解研究任务、证据标准与反证要求…")
        plan = current.research_plan_artifact or planning.generate_plan(current, brief)
        statuses = dict(current.workflow_status)
        statuses["research_planning"] = WorkflowStatus.COMPLETED
        statuses["evidence_collection"] = WorkflowStatus.IN_PROGRESS
        current = current.model_copy(
            update={
                "research_plan_artifact": plan,
                "workflow_status": statuses,
                "current_step": "evidence_collection",
                "updated_at": datetime.now(UTC),
            }
        )
        _save(current)
    except (ConfigurationError, ProviderError, SOPComplianceError, ValidationError) as exc:
        progress.empty()
        st.error(f"研究设计未完成：{exc}")
        return

    artifact = current.evidence_collection_artifact
    if artifact is not None and artifact.research_plan_id != plan.artifact_id:
        artifact = None
    completed_ids = {run.task_id for run in artifact.task_runs} if artifact else set()
    pending = [task for task in plan.tasks if task.task_id not in completed_ids]
    failures: list[str] = []
    for index, task in enumerate(pending, start=1):
        fraction = 0.15 + 0.8 * (index - 1) / max(len(pending), 1)
        progress.progress(fraction, text=f"正在检索 {task.task_id} · {task.title}")
        try:
            run = _run_task(current, task.task_id)
            artifact = upsert_task_run(artifact, plan.artifact_id, run)
            current = current.model_copy(
                update={
                    "evidence_collection_artifact": artifact,
                    "updated_at": datetime.now(UTC),
                }
            )
            _save(current)
        except (
            ConfigurationError,
            ProviderError,
            EvidenceCollectionError,
            ValidationError,
        ) as exc:
            reason = f"{task.task_id} · {task.title}：{exc}"
            failures.append(reason)
            artifact = upsert_task_run(
                artifact,
                plan.artifact_id,
                unresolved_task_run(current, task, str(exc)),
            )
        except Exception:
            # A cached provider created before a Streamlit hot reload can raise
            # an exception class with an obsolete runtime identity.  Treat the
            # provider boundary as untrusted and keep the remaining task queue
            # alive rather than exposing a framework traceback to the user.
            reason = f"{task.task_id} · {task.title}：本轮调用未形成可安全保存的结果"
            failures.append(reason)
            artifact = upsert_task_run(
                artifact,
                plan.artifact_id,
                unresolved_task_run(
                    current,
                    task,
                    "本轮调用未形成可安全保存的结果",
                ),
            )

        if artifact is not None:
            current = current.model_copy(
                update={
                    "evidence_collection_artifact": artifact,
                    "updated_at": datetime.now(UTC),
                }
            )
            _save(current)

    statuses = dict(current.workflow_status)
    remaining_gaps = evidence_coverage_gaps(artifact, plan)
    statuses["evidence_collection"] = WorkflowStatus.NEEDS_REVIEW
    statuses["evidence_qa"] = WorkflowStatus.NEEDS_REVIEW
    current = current.model_copy(
        update={
            "evidence_collection_artifact": artifact,
            "workflow_status": statuses,
            "current_step": "evidence_qa",
            "updated_at": datetime.now(UTC),
        }
    )
    _save(current)
    final_text = (
        "检索与逐问题覆盖检查完成，等待Gate 1人工确认"
        if artifact is not None and artifact.task_runs and not remaining_gaps
        else f"检索完成，识别出{len(remaining_gaps)}组证据缺口，可带着限制进入Gate 1"
        if remaining_gaps
        else "本轮检索没有形成可核验证据，将作为研究限制进入人工审核"
    )
    progress.progress(1.0, text=final_text)
    st.session_state["studio_pipeline_failures"] = failures
    st.rerun()


def _generate_content_drafts(project: ProjectState, evidence) -> None:
    statuses = _reset_strategy_statuses(
        project.workflow_status,
        enabled=project.company_strategy_enabled,
    )
    statuses["evidence_collection"] = WorkflowStatus.COMPLETED
    statuses["evidence_qa"] = WorkflowStatus.COMPLETED
    saved_gate = project.model_copy(
        update={
            "evidence_collection_artifact": evidence,
            **_strategy_output_reset(),
            "workflow_status": statuses,
            "last_pipeline_error": None,
            "updated_at": datetime.now(UTC),
        }
    )
    _save(saved_gate)
    try:
        with st.spinner("正在生成当前行业分析…"):
            analysis = industry_analysis_service().generate(saved_gate, evidence)
    except Exception as exc:
        diagnostic = str(exc).strip()[:260] or exc.__class__.__name__
        message = (
            "行业分析的结构检查未通过。Gate 1证据审核已经保存，无需重新搜索或逐条重审；"
            f"本次失败位置：行业分析组装；原因：{diagnostic}。"
        )
        statuses["industry_analysis"] = WorkflowStatus.BLOCKED
        failed = saved_gate.model_copy(
            update={
                "industry_analysis_artifact": None,
                "future_intelligence_artifact": None,
                "general_report_artifact": None,
                **_strategy_output_reset(),
                "workflow_status": statuses,
                "last_pipeline_error": message,
                "updated_at": datetime.now(UTC),
            }
        )
        _save(failed)
        st.error(message)
        return

    interim = saved_gate.model_copy(
        update={
            "industry_analysis_artifact": analysis,
            "future_intelligence_artifact": None,
            "general_report_artifact": None,
            **_strategy_output_reset(),
            "last_pipeline_error": None,
            "updated_at": datetime.now(UTC),
        }
    )
    _save(interim)
    try:
        with st.spinner("正在形成未来趋势、情景与反证条件…"):
            future = future_intelligence_service().generate(
                interim,
                evidence,
                analysis,
                allow_pending_findings=True,
            )
    except Exception as exc:
        diagnostic = str(exc).strip()[:260] or exc.__class__.__name__
        message = (
            "行业现状分析已经保存，但未来趋势本轮未能完成。无需重复网页检索或行业分析，"
            f"请直接点击“继续生成趋势”。失败原因：{diagnostic}。"
        )
        statuses = dict(interim.workflow_status)
        statuses["industry_analysis"] = WorkflowStatus.NEEDS_REVIEW
        statuses["future_intelligence"] = WorkflowStatus.BLOCKED
        failed = interim.model_copy(
            update={
                "future_intelligence_artifact": None,
                "general_report_artifact": None,
                **_strategy_output_reset(),
                "workflow_status": statuses,
                "last_pipeline_error": message,
                "updated_at": datetime.now(UTC),
            }
        )
        _save(failed)
        st.error(message)
        return
    statuses = dict(interim.workflow_status)
    statuses["evidence_collection"] = WorkflowStatus.COMPLETED
    statuses["evidence_qa"] = WorkflowStatus.COMPLETED
    statuses["industry_analysis"] = WorkflowStatus.NEEDS_REVIEW
    statuses["future_intelligence"] = WorkflowStatus.NEEDS_REVIEW
    updated = interim.model_copy(
        update={
            "future_intelligence_artifact": future,
            **_strategy_output_reset(),
            "workflow_status": statuses,
            "current_step": "human_review",
            "last_pipeline_error": None,
            "updated_at": datetime.now(UTC),
        }
    )
    _save(updated)
    st.rerun()


def _generate_future_draft(project: ProjectState) -> None:
    evidence = project.evidence_collection_artifact
    analysis = project.industry_analysis_artifact
    assert evidence is not None and analysis is not None
    try:
        with st.spinner("正在继续生成未来趋势、情景与反证条件…"):
            future = future_intelligence_service().generate(
                project,
                evidence,
                analysis,
                allow_pending_findings=True,
            )
    except Exception:
        message = "未来趋势本轮仍未完成；已保存的证据和行业分析不受影响，可以再次重试。"
        failed = project.model_copy(
            update={"last_pipeline_error": message, "updated_at": datetime.now(UTC)}
        )
        _save(failed)
        st.error(message)
        return
    statuses = dict(project.workflow_status)
    statuses = _reset_strategy_statuses(statuses, enabled=project.company_strategy_enabled)
    statuses["industry_analysis"] = WorkflowStatus.NEEDS_REVIEW
    statuses["future_intelligence"] = WorkflowStatus.NEEDS_REVIEW
    updated = project.model_copy(
        update={
            "future_intelligence_artifact": future,
            **_strategy_output_reset(),
            "workflow_status": statuses,
            "current_step": "human_review",
            "last_pipeline_error": None,
            "updated_at": datetime.now(UTC),
        }
    )
    _save(updated)
    st.rerun()


def _render_gate_one(project: ProjectState, advanced: bool) -> None:
    artifact = project.evidence_collection_artifact
    plan = project.research_plan_artifact
    assert artifact is not None and plan is not None
    advisories = evidence_coverage_advisories(artifact, plan)
    gap_resolution_code: str | None = None
    gap_user_input: str | None = None
    gap_resolution_ready = True
    if advisories:
        st.subheader("证据缺口与分析师处理建议")
        st.warning(
            "本轮检索未完全覆盖AI拆解出的所有问题，但证据缺口不会阻断研究。"
            "你可以直接审核现有证据并继续；后续分析会降低相关结论置信度，"
            "报告也会明确标注部分回答、证据边界和建议补数路径。"
        )
        st.dataframe(
            [
                {
                    "任务": item["task_id"],
                    "缺口类型": item["priority"],
                    "相对缺失的问题": item["missing_questions"],
                    "分析师处理建议": item["recommended_handling"],
                }
                for item in advisories
            ],
            hide_index=True,
            width="stretch",
        )
        resolution_choice = st.radio(
            "如何处理本轮证据缺口",
            ["接受分析师处理建议并带限制继续", "补充我的判断后继续"],
            horizontal=True,
            key=f"studio_gap_resolution_{artifact.artifact_id}",
        )
        if resolution_choice == "接受分析师处理建议并带限制继续":
            gap_resolution_code = "accept_analyst_handling"
        else:
            gap_resolution_code = "user_input"
            gap_user_input = st.text_area(
                "补充你的行业判断、内部观察或建议采用的口径",
                placeholder=(
                    "这些内容将作为待验证的专家输入进入分析，不会被冒充为公开事实。"
                ),
                key=f"studio_gap_user_input_{artifact.artifact_id}",
            ).strip()
        st.markdown(
            '<p style="color:#B42318;font-weight:800;margin-bottom:0.35rem;">'
            '请勾选确认，才能进行下一步（必选）</p>',
            unsafe_allow_html=True,
        )
        gap_acknowledged = st.checkbox(
            "我已阅读上述缺口及处理方式，并确认可以在这些证据边界下继续研究（必选）",
            key=f"studio_gap_acknowledged_{artifact.artifact_id}",
        )
        gap_resolution_ready = bool(
            gap_acknowledged
            and (
                gap_resolution_code == "accept_analyst_handling"
                or bool(gap_user_input)
            )
        )

    st.subheader("Gate 1 · 确认证据真实性与研究可用性")
    st.caption(
        "打开来源核对原文，并决定证据是否可以进入分析。快速模式给出系统推荐；最终采用决定必须由用户确认。"
    )
    source_map = {source.source_id: source for source in artifact.sources}
    recommended_ids = _recommended_evidence_ids(artifact, plan)
    selection_key = f"studio_gate_one_selection_{artifact.artifact_id}"
    version_key = f"studio_gate_one_editor_version_{artifact.artifact_id}"
    if selection_key not in st.session_state:
        st.session_state[selection_key] = set(recommended_ids)
    st.session_state.setdefault(version_key, 0)
    current_selection = set(st.session_state[selection_key])
    rows: list[dict] = []
    for item in artifact.evidence:
        source = source_map[item.source_id]
        rows.append(
            {
                "采用": item.evidence_id in current_selection,
                "Evidence ID": item.evidence_id,
                "任务": item.task_id,
                "类型": item.kind.value,
                "证据陈述": item.statement,
                "原文摘录": item.supporting_excerpt,
                "质量评分": item.qa_score,
                "问题相关度": round(item.prompt_relevance * 100),
                "对应研究问题": "、".join(
                    [*item.prompt_question_ids, *item.question_ids]
                ) or "旧项目：任务级映射",
                "来源": source.url,
            }
        )
    if not rows:
        st.warning(
            "首次完整检索没有形成可审阅网页证据。系统不会循环搜索或虚构结论；"
            "请提供可核验的一手资料后再进入证据审核。"
        )
    else:
        st.caption(
            f"共{len(rows)}条候选证据 · 系统推荐{len(recommended_ids)}条最小充分证据。"
            f"推荐资格：质量评分≥{MIN_GATE_ONE_QA}、问题相关度≥{MIN_PROMPT_RELEVANCE:.0%}；"
            "系统优先用较少且来源多样的证据覆盖全部研究问题，最终采用仍由你确认。"
        )
        with st.expander("质量评分如何计算", expanded=False):
            st.write(
                "质量评分满分100分，由五项可核验规则组成：来源及责任主体可追责性35分、"
                "原文可定位性25分、与已确认市场口径匹配20分、抽取置信度15分、"
                "时间信息完整性5分。问题相关度是独立指标，用于判断证据是否直接回答你的问题，"
                "不会用高质量但无关的材料凑数。"
            )
        bulk_a, bulk_b, bulk_c = st.columns(3)
        if bulk_a.button("采用全部系统推荐", width="stretch"):
            st.session_state[selection_key] = set(recommended_ids)
            st.session_state[version_key] += 1
            st.rerun()
        if bulk_b.button("一键全选", width="stretch"):
            st.session_state[selection_key] = {item.evidence_id for item in artifact.evidence}
            st.session_state[version_key] += 1
            st.rerun()
        if bulk_c.button("全部取消", width="stretch"):
            st.session_state[selection_key] = set()
            st.session_state[version_key] += 1
            st.rerun()
        edited = st.data_editor(
            rows,
            hide_index=True,
            width="stretch",
            disabled=[key for key in rows[0] if key != "采用"],
            column_config={
                "采用": st.column_config.CheckboxColumn("采用", help="由用户确认是否进入分析"),
                "来源": st.column_config.LinkColumn("来源"),
            },
            key=f"studio_gate_one_editor_{artifact.artifact_id}_{st.session_state[version_key]}",
        )
        if advanced:
            with st.expander("查看证据冲突、信息缺口与检索错误"):
                for run in artifact.task_runs:
                    if run.search_errors:
                        st.warning(f"{run.task_id}：" + "；".join(run.search_errors))
                    for conflict in run.conflicts:
                        st.write(f"- 冲突：{conflict.description}")
                    for gap in run.information_gaps:
                        st.write(f"- 缺口：{gap}")

        st.markdown(
            '<p style="color:#B42318;font-weight:800;margin-bottom:0.35rem;">'
            '请勾选确认，才能生成行业分析与趋势（必选）</p>',
            unsafe_allow_html=True,
        )
        truth_confirmed = st.checkbox(
            "我已检查拟采用证据的来源、原文和适用范围，并确认其可用于本次研究（必选）",
            key="studio_gate_one_truth_confirmation",
        )
        if st.button(
            "确认Gate 1并生成行业分析与趋势",
            type="primary",
            width="stretch",
            disabled=not truth_confirmed or not gap_resolution_ready,
        ):
            selected = {
                row["Evidence ID"] for row in _records(edited) if row.get("采用") is True
            }
            st.session_state[selection_key] = selected
            reviewed = artifact
            for item in artifact.evidence:
                status = (
                    EvidenceReviewStatus.ACCEPTED
                    if item.evidence_id in selected
                    else EvidenceReviewStatus.REJECTED
                )
                reviewed = review_evidence(
                    reviewed,
                    item.evidence_id,
                    status,
                    "Gate 1：用户确认来源、原文与研究可用性",
                )
            reasons = evidence_gate_reasons(reviewed, plan)
            if reasons:
                updated = project.model_copy(
                    update={
                        "evidence_collection_artifact": reviewed,
                        "updated_at": datetime.now(UTC),
                    }
                )
                _save(updated)
                st.error("Gate 1尚未通过：\n\n" + "\n\n".join(f"- {reason}" for reason in reasons))
            else:
                reviewed = reviewed.model_copy(
                    update={
                        "human_confirmed": True,
                        "coverage_gap_resolution": gap_resolution_code,
                        "coverage_gap_user_input": gap_user_input,
                        "coverage_gaps_acknowledged_at": (
                            datetime.now(UTC) if advisories else None
                        ),
                        "updated_at": datetime.now(UTC),
                    }
                )
                statuses = dict(project.workflow_status)
                statuses["evidence_collection"] = WorkflowStatus.COMPLETED
                statuses["evidence_qa"] = WorkflowStatus.COMPLETED
                gate_project = project.model_copy(
                    update={
                        "evidence_collection_artifact": reviewed,
                        "workflow_status": statuses,
                        "last_pipeline_error": None,
                        "updated_at": datetime.now(UTC),
                    }
                )
                _save(gate_project)
                _generate_content_drafts(gate_project, reviewed)

def _render_gate_two(project: ProjectState, advanced: bool) -> None:
    analysis = project.industry_analysis_artifact
    future = project.future_intelligence_artifact
    assert analysis is not None and future is not None
    st.subheader("Gate 2 · 确认进入报告的分析内容")
    st.caption("这里确认的是行业判断、趋势和情景，不是再次确认网页来源。未选内容不会进入最终报告。")

    finding_rows = [
        {
            "进入报告": item.review_status != AnalysisReviewStatus.REJECTED,
            "Finding ID": item.finding_id,
            "模块": module.title,
            "类型": item.finding_type.value,
            "判断": item.statement,
            "机制": item.mechanism,
            "置信度": item.confidence,
            "不确定性": item.uncertainty,
        }
        for module in analysis.modules
        for item in module.findings
    ] + [
        {
            "进入报告": item.review_status == AnalysisReviewStatus.ACCEPTED,
            "Finding ID": item.finding_id,
            "模块": "目标企业初步影响（非公司评分）",
            "类型": item.finding_type.value,
            "判断": item.statement,
            "机制": item.mechanism,
            "置信度": item.confidence,
            "不确定性": item.uncertainty,
        }
        for item in analysis.company_implications
    ]
    st.markdown("#### 行业现状、竞争者、驱动与商业逻辑")
    with st.expander("先阅读五个分析模块摘要", expanded=not advanced):
        for module in analysis.modules:
            st.markdown(f"**{module.title}**")
            st.write(module.executive_summary)
    edited_findings = st.data_editor(
        finding_rows,
        hide_index=True,
        width="stretch",
        disabled=[key for key in finding_rows[0] if key != "进入报告"] if finding_rows else True,
        column_config={"进入报告": st.column_config.CheckboxColumn("进入报告")},
        key="studio_gate_two_findings",
    ) if finding_rows else []

    future_rows = [
        {
            "进入报告": item.review_status != ForecastReviewStatus.REJECTED,
            "ID": item.trend_id,
            "内容类型": "趋势",
            "标题": item.title,
            "核心内容": item.forecast_statement,
            "置信度/可能性": f"{item.confidence.overall}/100",
        }
        for item in future.trends
    ] + [
        {
            "进入报告": item.review_status != ForecastReviewStatus.REJECTED,
            "ID": item.scenario_id,
            "内容类型": f"情景 · {item.scenario_type.value}",
            "标题": item.title,
            "核心内容": item.narrative,
            "置信度/可能性": item.likelihood_label,
        }
        for item in future.scenarios
    ]
    st.markdown("#### 未来趋势与情景")
    edited_future = st.data_editor(
        future_rows,
        hide_index=True,
        width="stretch",
        disabled=[key for key in future_rows[0] if key != "进入报告"],
        column_config={"进入报告": st.column_config.CheckboxColumn("进入报告")},
        key="studio_gate_two_future",
    )
    if advanced:
        with st.expander("查看跨模块冲突、预测缺口与监测重点"):
            for item in analysis.cross_module_conflicts:
                st.write(f"- 冲突：{item}")
            for item in analysis.overall_evidence_limitations:
                st.write(f"- 局限：{item}")
            for item in future.forecast_gaps:
                st.write(f"- 预测缺口：{item}")
            for item in future.monitoring_priorities:
                st.write(f"- 监测：{item}")

    content_confirmed = st.checkbox(
        "我已审阅拟进入报告的行业判断、趋势、情景、风险和局限",
        key="studio_gate_two_confirmation",
    )
    if st.button(
        "确认Gate 2并生成通用行业报告",
        type="primary",
        width="stretch",
        disabled=not content_confirmed,
    ):
        selected_findings = {
            row["Finding ID"]
            for row in _records(edited_findings)
            if row.get("进入报告") is True
        }
        selected_future = {
            row["ID"] for row in _records(edited_future) if row.get("进入报告") is True
        }
        selected_trends = {item.trend_id for item in future.trends if item.trend_id in selected_future}
        dependency_errors: list[str] = []
        for trend in future.trends:
            if trend.trend_id in selected_trends:
                missing = set(trend.finding_ids) - selected_findings
                if missing:
                    dependency_errors.append(
                        f"趋势 {trend.trend_id} 仍引用未采用判断：{', '.join(sorted(missing))}"
                    )
        for scenario in future.scenarios:
            if scenario.scenario_id in selected_future:
                missing_trends = set(scenario.trend_ids) - selected_trends
                if missing_trends:
                    dependency_errors.append(
                        f"情景 {scenario.scenario_id} 仍引用未采用趋势：{', '.join(sorted(missing_trends))}"
                    )
        if dependency_errors:
            st.error("内容依赖尚未闭合：\n\n" + "\n\n".join(f"- {item}" for item in dependency_errors))
            return

        reviewed_analysis = analysis
        for finding in analysis.findings:
            reviewed_analysis = review_analysis_finding(
                reviewed_analysis,
                finding.finding_id,
                AnalysisReviewStatus.ACCEPTED
                if finding.finding_id in selected_findings
                else AnalysisReviewStatus.REJECTED,
                "Gate 2：用户确认是否进入通用行业报告",
            )
        analysis_reasons = analysis_gate_reasons(reviewed_analysis)
        if analysis_reasons:
            st.error("行业分析尚未通过：\n\n" + "\n\n".join(f"- {item}" for item in analysis_reasons))
            return
        reviewed_analysis = reviewed_analysis.model_copy(
            update={"human_confirmed": True, "updated_at": datetime.now(UTC)}
        )

        reviewed_future = future
        for item in [*future.trends, *future.scenarios]:
            item_id = item.trend_id if hasattr(item, "trend_id") else item.scenario_id
            reviewed_future = review_forecast_item(
                reviewed_future,
                item_id,
                ForecastReviewStatus.ACCEPTED
                if item_id in selected_future
                else ForecastReviewStatus.REJECTED,
                "Gate 2：用户确认是否进入通用行业报告",
            )
        future_reasons = forecast_gate_reasons(reviewed_future)
        if future_reasons:
            st.error("未来趋势尚未通过：\n\n" + "\n\n".join(f"- {item}" for item in future_reasons))
            return
        reviewed_future = reviewed_future.model_copy(
            update={"human_confirmed": True, "updated_at": datetime.now(UTC)}
        )

        statuses = dict(project.workflow_status)
        statuses = _reset_strategy_statuses(statuses, enabled=project.company_strategy_enabled)
        statuses["industry_analysis"] = WorkflowStatus.COMPLETED
        statuses["future_intelligence"] = WorkflowStatus.COMPLETED
        statuses["human_review"] = WorkflowStatus.COMPLETED
        statuses["decision_report"] = WorkflowStatus.READY
        reviewed_project = project.model_copy(
            update={
                "industry_analysis_artifact": reviewed_analysis,
                "future_intelligence_artifact": reviewed_future,
                **_strategy_output_reset(),
                "workflow_status": statuses,
                "current_step": "decision_report",
                "updated_at": datetime.now(UTC),
            }
        )
        try:
            with st.spinner("正在检查研究重点覆盖情况并组织专业行业报告…"):
                report = report_generation_service().generate(reviewed_project)
        except Exception:
            st.error("报告本轮未能完成。已审核内容均已保存，可以直接重新生成报告。")
            return
        statuses["decision_report"] = WorkflowStatus.COMPLETED
        reviewed_project = reviewed_project.model_copy(
            update={
                "general_report_artifact": report,
                "enterprise_decision_report_artifact": None,
                "workflow_status": statuses,
                "updated_at": datetime.now(UTC),
            }
        )
        _save(reviewed_project)
        st.rerun()


def _render_report(project: ProjectState) -> None:
    report = project.general_report_artifact
    assert report is not None
    st.success("通用行业报告已经生成，并完成市场口径、证据和报告内容三道人工确认。")
    cols = st.columns(4)
    cols[0].metric("采用证据", len(report.accepted_evidence_ids))
    cols[1].metric("采用判断", len(report.accepted_finding_ids))
    cols[2].metric("独立来源", report.source_count)
    answered = sum(item.coverage_status == "answered" for item in report.prompt_coverage)
    cols[3].metric("研究重点覆盖", f"{answered}/{len(report.prompt_coverage)}")
    if report.unresolved_prompt_questions:
        st.warning(
            "以下研究重点仍存在部分覆盖或证据缺口："
            + "；".join(report.unresolved_prompt_questions)
        )
    report_style = render_report_preview(
        report.markdown,
        key=f"consultant_{project.project_id}",
        expanded=True,
    )
    safe_name = "-".join(project.project_name.split()) or "industry-report"
    export_context = project_report_context(
        project,
        title=report.title,
        markdown=report.markdown,
        report_status="经人工审核的通用行业研究报告",
        generated_at=report.generated_at,
        style=report_style,
    )
    col_a, col_b = st.columns(2)
    try:
        word_report = build_report_docx(export_context)
    except Exception:
        col_a.error("Word 报告暂时无法生成，研究报告正文已保存。")
    else:
        col_a.download_button(
            "下载 Word 报告",
            data=word_report,
            file_name=f"{safe_name}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch",
            type="primary",
        )
    try:
        pdf_report = build_report_pdf(export_context)
    except Exception:
        col_b.error("PDF 报告暂时无法生成；Word 下载不受影响。")
    else:
        col_b.download_button(
            "下载 PDF 报告",
            data=pdf_report,
            file_name=f"{safe_name}.pdf",
            mime="application/pdf",
            width="stretch",
            type="primary",
        )
    if project.company_strategy_enabled:
        st.markdown("### 继续企业战略分析")
        reasons = company_scorecard_eligibility(project)
        if reasons:
            st.info(
                "通用行业报告已经完成。企业评分还需要补齐："
                + "；".join(reasons)
            )
            if st.button("补充或确认 Enterprise Sensing", width="stretch"):
                queue_page_navigation(st.session_state, "enterprise_sensing")
                st.rerun()
        elif st.button("进入 Company Scorecard", type="primary", width="stretch"):
            queue_page_navigation(st.session_state, "company_scorecard")
            st.rerun()


def _run_reviewer_report_pipeline(project: ProjectState) -> None:
    """Generate a report-first draft and its complete trace package.

    Reviewer mode does not expose intermediate generation gates. The locked
    research SOP and validation services still run; the resulting evidence,
    analysis, forecast and strategy artifacts are presented afterward as an
    auditable workpaper rather than as a sequence the reviewer must operate.
    """

    progress_labels = {
        "research_plan": "正在按照最新SOP拆解研究范围…",
        "reference_collection": "已完成网页研究，正在整理Reference Matrix…",
        "industry_analysis": "正在生成行业定义、赛道、规模与竞争格局分析…",
        "future_intelligence": "正在形成未来趋势、情景和可证伪条件…",
        "general_report": "正在组织完整行业研究报告…",
        "company_scorecard": "正在形成 Company Scorecard…",
        "action_plan": "正在根据企业战略意图形成 Action Plan…",
        "enterprise_report": "正在组织企业决策报告…",
    }
    progress = st.progress(0, text="正在准备审阅式研究的报告优先流程…")

    def update_progress(stage: str, completed: int, total: int) -> None:
        progress.progress(
            completed / max(total, 1),
            text=progress_labels.get(stage, f"正在完成 {stage}…"),
        )

    try:
        result = asyncio.run(
            reviewer_orchestration_service().run(
                project,
                enterprise=project.company_strategy_enabled,
                on_progress=update_progress,
            )
        )
    except ReviewerPipelineError as exc:
        _save(exc.project)
        progress.empty()
        st.error(
            f"完整报告本轮未能生成：{exc}。已完成的研究底稿已经保存，"
            "再次运行时不会重复已经完成的网页检索。"
        )
        return
    except Exception as exc:
        progress.empty()
        st.error(f"完整报告本轮未能生成：{str(exc).strip()[:320] or exc.__class__.__name__}")
        return

    _save(result.project)
    progress.progress(1.0, text="完整报告和全部可追溯底稿已经生成")
    if result.warnings:
        st.session_state[f"reviewer_warnings_{project.project_id}"] = list(result.warnings)
    st.rerun()


def _rerun_reviewer_analysis(project: ProjectState) -> None:
    """Regenerate analytical layers under the latest SOP without new searching."""

    statuses = dict(project.workflow_status)
    for step in ("industry_analysis", "future_intelligence", "decision_report"):
        statuses[step] = WorkflowStatus.NOT_STARTED
    refreshed = project.model_copy(
        update={
            "industry_analysis_artifact": None,
            "future_intelligence_artifact": None,
            "general_report_artifact": None,
            "company_scorecard_artifact": None,
            "action_plan_artifact": None,
            "enterprise_decision_report_artifact": None,
            "content_revision_artifact": None,
            "workflow_status": statuses,
            "last_pipeline_error": None,
            "updated_at": datetime.now(UTC),
        }
    )
    _save(refreshed)
    _run_reviewer_report_pipeline(refreshed)


def _render_reviewer_report_downloads(
    project: ProjectState,
    markdown: str,
    title: str,
    report_style,
) -> None:
    safe_name = "-".join(project.project_name.split()) or "industry-report"
    export_context = project_report_context(
        project,
        title=title,
        markdown=markdown,
        report_status="审阅式研究初稿 · 待完成追溯检查",
        generated_at=(
            project.enterprise_decision_report_artifact.generated_at
            if project.company_strategy_enabled and project.enterprise_decision_report_artifact
            else project.general_report_artifact.generated_at
        ),
        style=report_style,
    )
    word_col, pdf_col = st.columns(2)
    try:
        word_payload = build_report_docx(export_context)
    except Exception:
        word_col.error("Word 报告暂时无法生成。")
    else:
        word_col.download_button(
            "下载 Word 审阅稿",
            word_payload,
            file_name=f"{safe_name}.review-draft.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch",
            type="primary",
        )
    try:
        pdf_payload = build_report_pdf(export_context)
    except Exception:
        pdf_col.error("PDF 报告暂时无法生成。")
    else:
        pdf_col.download_button(
            "下载 PDF 审阅稿",
            pdf_payload,
            file_name=f"{safe_name}.review-draft.pdf",
            mime="application/pdf",
            width="stretch",
            type="primary",
        )


def _reference_check_items(project: ProjectState):
    """Return the sources actually used by the report-first draft.

    Reviewer orchestration deliberately keeps persisted review decisions in
    ``needs_review``.  The temporary accepted copy exists only while generating
    the report, so filtering the saved matrix by human review status would make
    Reference Check appear empty.  The report's accepted-ID ledger is the
    durable trace contract; older reports without that ledger fall back to all
    non-rejected candidates.
    """

    artifact = project.evidence_collection_artifact
    if artifact is None:
        return []
    report = project.general_report_artifact
    report_ids = set(report.accepted_evidence_ids) if report else set()
    if report_ids:
        return [item for item in artifact.evidence if item.evidence_id in report_ids]
    return [
        item
        for item in artifact.evidence
        if item.review_status != EvidenceReviewStatus.REJECTED
    ]


def _render_reference_check(project: ProjectState) -> None:
    artifact = project.evidence_collection_artifact
    if artifact is None:
        st.info("尚未形成网页引用资料。")
        return
    source_map = {source.source_id: source for source in artifact.sources}
    accepted = _reference_check_items(project)
    st.caption(
        "Reference Check展示报告草稿实际采用的网页资料、原文摘录与适用范围。"
        "系统纳入草稿不等于人工确认；这里用于追溯审阅，不会重新执行搜索。"
    )
    st.dataframe(
        [
            {
                "研究主题": item.task_id,
                "引用内容": item.statement,
                "原文摘录": item.supporting_excerpt,
                "适用范围": f"{item.geographic_scope} · {item.market_scope}",
                "质量": item.qa_score,
                "来源": source_map[item.source_id].url,
            }
            for item in accepted
            if item.source_id in source_map
        ],
        hide_index=True,
        width="stretch",
        column_config={"来源": st.column_config.LinkColumn("来源")},
    )
    gaps = evidence_coverage_advisories(artifact, project.research_plan_artifact)
    if gaps:
        with st.expander("查看需要重点复核的问题与当前处理方式"):
            for item in gaps:
                st.write(
                    f"- {item['task_id']}：{item['missing_questions']}。当前处理：{item['recommended_handling']}"
                )


def _render_analysis_trace(project: ProjectState) -> None:
    analysis = project.industry_analysis_artifact
    if analysis is None:
        st.info("尚未形成行业分析底稿。")
        return
    st.caption("以下内容解释正式报告中的行业定义、产业链、规模、竞争格局和驱动因素如何形成。")
    st.markdown("### 市场规模测算逻辑")
    st.caption(
        "主方法按细分市场的数量与加权平均价格计算，自上而下方法用于独立校验；"
        "表中同时记录统计口径和去重规则，避免上下游收入或新增与替换需求重复加总。"
    )
    st.dataframe(
        market_sizing_calculation_rows(analysis),
        hide_index=True,
        width="stretch",
    )
    for module in analysis.modules:
        with st.expander(module.title, expanded=False):
            st.write(module.executive_summary)
            for finding in module.findings:
                st.markdown(f"**{finding.statement}**")
                st.write(finding.mechanism)
                st.caption(
                    f"置信度 {finding.confidence:.0%} · 适用边界：{finding.boundary_condition} · 不确定性：{finding.uncertainty}"
                )
    with st.expander("查看SOP方法记录"):
        st.write("适用规则：" + "、".join(analysis.methodology.rule_ids))
        for check in analysis.methodology.compliance_checks:
            st.write(f"- {check}")


def _render_future_trace(project: ProjectState) -> None:
    future = project.future_intelligence_artifact
    if future is None:
        st.info("尚未形成 Future Intelligence。")
        return
    methodology = future.forecast_methodology
    st.caption(
        f"预测方法：{methodology.selected_method.value} · 结构化观测 {methodology.structured_observation_count} 条 · "
        f"量化模型{'已运行' if methodology.quantitative_forecast_used else '未运行，采用因果情景法'}"
    )
    for trend in future.trends:
        with st.expander(trend.title, expanded=False):
            st.write(trend.forecast_statement)
            st.markdown("**因果机制**")
            for step in trend.causal_mechanism:
                st.write(f"- {step}")
            st.write("**反证条件：** " + "；".join(trend.falsification_conditions))
            st.caption(f"预测置信度：{trend.confidence.overall}/100")
    st.markdown("#### 情景分析")
    for scenario in future.scenarios:
        st.markdown(f"**{scenario.title} · {scenario.likelihood_label}**")
        st.write(scenario.narrative)


def _render_scorecard_trace(project: ProjectState) -> None:
    scorecard = project.company_scorecard_artifact
    if scorecard is None:
        st.info("尚未形成 Company Scorecard。")
        return
    score_cols = st.columns(3)
    score_cols[0].metric(
        "企业综合评分",
        f"{scorecard.weighted_score:.1f}" if scorecard.weighted_score is not None else "资料不足",
    )
    weighted_benchmark_score = getattr(scorecard, "weighted_benchmark_score", None)
    weighted_gap = getattr(scorecard, "weighted_gap", None)
    score_cols[1].metric(
        "市场基准分",
        f"{weighted_benchmark_score:.1f}"
        if weighted_benchmark_score is not None
        else "资料不足",
    )
    score_cols[2].metric(
        "基准差距",
        f"{weighted_gap:+.1f}" if weighted_gap is not None else "资料不足",
    )
    st.write(scorecard.overall_assessment)
    render_scorecard_radar(scorecard, key=f"review_scorecard_radar_{scorecard.artifact_id}")
    st.dataframe(
        [
            {
                "评估维度": item.title,
                "得分": item.score,
                "市场基准分": getattr(item, "benchmark_score", None),
                "基准差距": getattr(item, "benchmark_gap", None),
                "市场位置": getattr(item, "market_position_label", ""),
                "权重": f"{item.weight:.0%}",
                "置信度": item.confidence,
                "主要优势": "；".join(item.strengths),
                "关键差距": "；".join(item.gaps),
                "当前市场位置": item.current_market_position,
                "战略目标状态": item.target_position,
                "战略差距": item.strategic_gap,
            }
            for item in scorecard.dimensions
        ],
        hide_index=True,
        width="stretch",
    )


def _render_action_plan_trace(project: ProjectState) -> None:
    plan = project.action_plan_artifact
    if plan is None:
        st.info("尚未形成 Action Plan。")
        return
    st.caption("所有行动均以用户填写的企业战略意图为约束，并连接公司评分、公开证据、企业资料和趋势。")
    for action in plan.actions:
        with st.expander(f"{action.priority.value.upper()} · {action.title}"):
            st.write(action.rationale)
            st.write(f"**责任主体：** {action.owner_role} · **时间：** {action.timing}")
            st.write("**资源：** " + "；".join(action.resources))
            st.write("**停止或转向条件：** " + "；".join(action.stop_conditions))
            st.dataframe(
                [
                    {
                        "指标类型": kpi.kpi_type.value,
                        "指标": kpi.name,
                        "目标": kpi.target,
                        "时间": kpi.timing,
                        "数据源": kpi.data_source,
                    }
                    for kpi in action.kpis
                ],
                hide_index=True,
                width="stretch",
            )


def _render_content_revision(project: ProjectState, report) -> None:
    """Let a Reviewer iterate on the whole report and its reasoning traces."""

    artifact = initialize_revision(project)
    if project.content_revision_artifact is None:
        project = project.model_copy(update={"content_revision_artifact": artifact})
        _save(project)

    st.subheader("Content Revision · 报告修改与审阅会话")
    st.caption(
        "可直接修改报告，也可针对引用、行业分析、未来趋势及企业决策逻辑向AI提出疑问。"
        "接受建议后会生成一个新版本；该过程可以反复进行。"
    )
    attention = reviewer_attention_points(project)
    with st.expander("报告注意点（仅供审阅，不会进入正式报告）", expanded=bool(attention)):
        if attention:
            for item in attention:
                st.write(f"- {item}")
        else:
            st.write("当前未发现需要额外提示的结构性审阅事项。")

    draft_key = f"reviewer_report_draft_{project.project_id}_{artifact.active_version}"
    edited = st.text_area(
        "直接编辑完整报告",
        value=report.markdown,
        height=620,
        key=draft_key,
    )
    direct_col, final_col = st.columns(2)
    if direct_col.button(
        "保存为新版本",
        type="primary",
        width="stretch",
        key=f"reviewer_save_direct_{project.project_id}_{artifact.active_version}",
    ):
        try:
            updated = save_report_version(
                project,
                edited,
                source="direct_edit",
                reviewer_note="审阅式研究直接编辑",
            )
        except ReviewerRevisionError as exc:
            st.error(str(exc))
        else:
            _save(updated)
            st.rerun()
    final_label = "重新开启修改" if artifact.finalized else "当前版本审阅完成"
    if final_col.button(
        final_label,
        width="stretch",
        key=f"reviewer_finalize_{project.project_id}_{artifact.finalized}",
    ):
        _save(finalize_revision(project, not artifact.finalized))
        st.rerun()

    st.markdown("### 向AI提出审阅意见或疑问")
    target_options = [
        RevisionTarget.REPORT,
        RevisionTarget.REFERENCE_CHECK,
        RevisionTarget.INDUSTRY_ANALYSIS,
        RevisionTarget.FUTURE_INTELLIGENCE,
    ]
    if project.company_strategy_enabled:
        target_options.extend([RevisionTarget.COMPANY_SCORECARD, RevisionTarget.ACTION_PLAN])
    target_labels = {
        RevisionTarget.REPORT: "完整报告",
        RevisionTarget.REFERENCE_CHECK: "Reference Check",
        RevisionTarget.INDUSTRY_ANALYSIS: "Industry Analysis",
        RevisionTarget.FUTURE_INTELLIGENCE: "Future Intelligence",
        RevisionTarget.COMPANY_SCORECARD: "Company Scorecard",
        RevisionTarget.ACTION_PLAN: "Action Plan",
    }
    targets = st.multiselect(
        "本轮审阅范围",
        target_options,
        default=[],
        format_func=target_labels.get,
        key=f"reviewer_targets_{project.project_id}_{len(artifact.turns)}",
    )
    st.caption("只会修改本轮选中的模块；未选章节、Company Scorecard和Action Plan将保持原样。")
    message = st.text_area(
        "审阅意见、疑问或希望调整的观点",
        placeholder="例如：竞争格局需要增加国际玩家与国产头部公司的分层比较，并重新判断国产替代节奏。",
        key=f"reviewer_message_{project.project_id}_{len(artifact.turns)}",
    )
    if st.button(
        "让AI分析并提出新版本",
        type="primary",
        width="stretch",
        key=f"reviewer_analyze_{project.project_id}_{len(artifact.turns)}",
    ):
        try:
            with st.spinner("正在回到原始Prompt并分析本轮审阅意见…"):
                if not targets:
                    raise ReviewerRevisionError("请至少选择一个本轮审阅范围")
                revised = reviewer_revision_service().analyze(
                    project,
                    message,
                    targets,
                    direct_draft=edited,
                )
        except ReviewerRevisionError as exc:
            st.error(str(exc))
        else:
            _save(project.model_copy(update={"content_revision_artifact": revised}))
            st.rerun()

    artifact = project.content_revision_artifact or artifact
    if artifact.turns:
        st.markdown("### 审阅会话")
        for index, turn in enumerate(reversed(artifact.turns), start=1):
            round_number = len(artifact.turns) - index + 1
            with st.expander(
                f"第{round_number}轮 · {'已采纳' if turn.accepted else '待确认'} · {turn.reviewer_message[:46]}",
                expanded=index == 1,
            ):
                st.markdown("**AI对问题的分析**")
                st.write(turn.assistant_analysis)
                if turn.recommendations:
                    st.markdown("**推荐观点**")
                    for item in turn.recommendations:
                        st.write(f"- {item}")
                if turn.questions_for_reviewer:
                    st.markdown("**需要人工判断**")
                    for item in turn.questions_for_reviewer:
                        st.write(f"- {item}")
                if turn.trace_amendments:
                    st.markdown("**研究逻辑修订记录**")
                    for target, amendment in turn.trace_amendments.items():
                        st.write(f"- {target}：{amendment}")
                st.markdown("**建议的新版本报告**")
                st.markdown(turn.proposed_markdown)
                if not turn.accepted and turn.turn_id == artifact.turns[-1].turn_id:
                    accept_col, continue_col = st.columns(2)
                    if accept_col.button(
                        "接受建议并生成新版本",
                        type="primary",
                        width="stretch",
                        key=f"accept_revision_{turn.turn_id}",
                    ):
                        updated = save_report_version(
                            project,
                            turn.proposed_markdown,
                            source="ai_revision",
                            reviewer_note=turn.reviewer_message,
                            accept_latest_turn=True,
                        )
                        _save(updated)
                        st.rerun()
                    continue_col.caption("如不接受，继续在上方提出下一轮疑问或修改方向。")

    if artifact.versions:
        with st.expander("查看版本历史"):
            for version in reversed(artifact.versions):
                st.write(
                    f"V{version.version} · {version.source} · "
                    f"{version.created_at.strftime('%Y-%m-%d %H:%M')}"
                )


def _render_reviewer_workpapers(project: ProjectState) -> None:
    report = (
        project.enterprise_decision_report_artifact
        if project.company_strategy_enabled
        else project.general_report_artifact
    )
    if report is None:
        st.info("研究范围已确认。点击下方按钮即可一次生成完整报告和全部可追溯底稿。")
        if st.button(
            "生成完整报告及可追溯底稿",
            type="primary",
            width="stretch",
            key=f"reviewer_generate_{project.project_id}",
        ):
            _run_reviewer_report_pipeline(project)
        return

    labels = ["完整报告", "Content Revision", "Reference Check", "Industry Analysis", "Future Intelligence"]
    if project.company_strategy_enabled:
        labels.extend(["Company Scorecard", "Action Plan"])
    tabs = st.tabs(labels)
    with tabs[0]:
        st.info("这是报告优先生成的审阅稿。其余页签用于追溯引用、分析方法和决策逻辑。")
        if project.company_strategy_enabled and project.company_scorecard_artifact is not None:
            st.markdown("### 公司得分与市场基准")
            render_scorecard_radar(
                project.company_scorecard_artifact,
                key=f"reviewer_report_radar_{project.project_id}",
            )
        report_style = render_report_preview(
            report.markdown,
            key=f"reviewer_{project.project_id}",
            expanded=True,
            label="预览完整审阅稿",
        )
        _render_reviewer_report_downloads(
            project,
            report.markdown,
            report.title,
            report_style,
        )
        if st.button(
            "按最新SOP重新生成分析与报告",
            width="stretch",
            key=f"reviewer_regenerate_latest_{project.project_id}",
        ):
            _rerun_reviewer_analysis(project)
    with tabs[1]:
        _render_content_revision(project, report)
    with tabs[2]:
        _render_reference_check(project)
    with tabs[3]:
        _render_analysis_trace(project)
    with tabs[4]:
        _render_future_trace(project)
    if project.company_strategy_enabled:
        with tabs[5]:
            _render_scorecard_trace(project)
        with tabs[6]:
            _render_action_plan_trace(project)


def _render_reviewer_workspace(project: ProjectState) -> None:
    st.markdown(
        '<div class="ia-reviewer-banner"><strong>审阅式研究 · Report Review First</strong>'
        '<span>先看完整报告，再追溯引用、分析方法与企业决策依据</span></div>',
        unsafe_allow_html=True,
    )
    _render_progress(project)
    if project.company_strategy_enabled and company_strategy_gate_reasons(project):
        st.warning("企业战略报告需要先接入并确认企业资料。完成后将返回本页生成完整报告。")
        if st.button("接入或审核企业资料", type="primary", width="stretch"):
            queue_page_navigation(st.session_state, "enterprise_sensing")
            st.rerun()
        return
    with st.expander("研究需求与范围", expanded=project.research_brief_artifact is None):
        st.write(f"**行业：** {project.industry} · **地区：** {project.region}")
        st.write(f"**原始研究需求：** {project.research_objective}")
        if project.company_strategy_enabled:
            st.write(f"**企业战略意图：** {project.company_strategy_objective}")
    brief = project.research_brief_artifact
    if brief is None:
        if st.button("AI分析研究需求并生成市场描述", type="primary", width="stretch"):
            _generate_research_brief(project)
    elif not brief.human_confirmed:
        _render_gate_zero(project, reviewer_mode=True)
    else:
        _render_reviewer_workpapers(project)


def render(project: ProjectState | None) -> None:
    role = get_user_role(st.session_state) or UserRole.CONSULTANT
    if role == UserRole.REVIEWER:
        page_header(
            "Report Review First",
            "报告审阅工作台",
            "确认研究范围后先查看完整报告，再按引用、分析方法和决策逻辑追溯研究过程",
        )
    else:
        page_header(
            "Research Studio · Three Human Gates",
            "行业研究工作台",
            "通用报告与高级分析师模式可以相互切换，且已经完成的研究部分不会丢失",
        )
    if not require_project(project):
        return
    assert project is not None

    if role == UserRole.REVIEWER:
        _render_reviewer_workspace(project)
        return

    if project.company_strategy_enabled:
        advanced = True
        if project.workspace_mode != WorkspaceMode.ANALYST_WORKSPACE:
            project = project.model_copy(
                update={"workspace_mode": WorkspaceMode.ANALYST_WORKSPACE, "updated_at": datetime.now(UTC)}
            )
            _save(project)
        st.markdown("**工作模式：高级分析师工作台（企业战略项目）**")
    else:
        selected_mode = st.segmented_control(
            "工作模式",
            list(WorkspaceMode),
            default=project.workspace_mode,
            format_func=MODE_LABELS.get,
            width="stretch",
        )
        if selected_mode is not None and selected_mode != project.workspace_mode:
            updated = project.model_copy(
                update={"workspace_mode": selected_mode, "updated_at": datetime.now(UTC)}
            )
            _save(updated)
            st.rerun()
        advanced = project.workspace_mode == WorkspaceMode.ANALYST_WORKSPACE

    if advanced:
        st.info("高级工作台已启用：先确认企业战略意图和一手资料，再执行行业研究，并将结果联动至Company Scorecard和Action Plan。")
        _render_advanced_context(project)
    else:
        st.info("快速通用报告：依次确认市场口径、网页证据和报告内容，其他步骤自动衔接。")

    _render_progress(project)
    if project.company_strategy_enabled and company_strategy_gate_reasons(project):
        st.warning("企业战略研究的前置资料尚未通过确认。请先点击上方“接入或审核企业一手数据”；完成后将从本页继续研究，进度不会丢失。")
        return
    rewind_notice = st.session_state.pop("studio_rewind_notice", None)
    if rewind_notice:
        st.success(rewind_notice)
    _render_rewind_control(project)
    failures = st.session_state.pop("studio_pipeline_failures", [])
    if failures:
        st.warning(
            "部分任务未形成可核验证据，已作为研究限制进入Gate 1：\n\n"
            + "\n\n".join(f"- {item}" for item in failures)
        )
    if project.last_pipeline_error:
        st.warning(project.last_pipeline_error)

    with st.expander("研究目标与执行边界", expanded=project.research_plan_artifact is None):
        st.write(f"**行业：** {project.industry} · **地区：** {project.region}")
        st.write(f"**研究目标：** {project.research_objective}")
        st.write(f"**时间范围：** {project.time_horizon}")
        st.caption("第一步只调用语言模型理解原始Prompt并生成市场描述，不会立即搜索网页。")

    brief = project.research_brief_artifact
    plan = project.research_plan_artifact
    evidence = project.evidence_collection_artifact
    if brief is None:
        if st.button("AI分析研究需求并生成市场描述", type="primary", width="stretch"):
            _generate_research_brief(project)
    elif not brief.human_confirmed:
        _render_gate_zero(project)
    elif plan is None or evidence is None:
        start_label = "按照已确认口径执行完整网页研究"
        if st.button(
            start_label,
            type="primary",
            width="stretch",
        ):
            _run_research_design_and_search(project)
    else:
        if not evidence.human_confirmed:
            _render_gate_one(project, advanced)
        elif project.industry_analysis_artifact is None:
            st.success("Gate 1已经通过。")
            if st.button("重新生成行业分析与趋势", type="primary", width="stretch"):
                _generate_content_drafts(project, evidence)
        elif project.future_intelligence_artifact is None:
            st.success("Gate 1与行业现状分析已经保存。")
            if st.button("继续生成未来趋势", type="primary", width="stretch"):
                _generate_future_draft(project)
        elif not (
            project.industry_analysis_artifact.human_confirmed
            and project.future_intelligence_artifact.human_confirmed
        ):
            _render_gate_two(project, advanced)
        elif project.general_report_artifact is None:
            report_label = (
                "完成行业研究底稿并进入 Company Scorecard"
                if project.company_strategy_enabled
                else "生成通用行业报告"
            )
            if st.button(report_label, type="primary", width="stretch"):
                try:
                    with st.spinner("正在逐题检查原始Prompt覆盖情况并生成报告…"):
                        report = report_generation_service().generate(project)
                except Exception:
                    st.error("报告本轮未能完成。已审核内容没有丢失，请直接再次生成。")
                else:
                    statuses = dict(project.workflow_status)
                    statuses["decision_report"] = WorkflowStatus.COMPLETED
                    updated = project.model_copy(
                        update={
                            "general_report_artifact": report,
                            "enterprise_decision_report_artifact": None,
                            "workflow_status": statuses,
                            "updated_at": datetime.now(UTC),
                        }
                    )
                    _save(updated)
                    if project.company_strategy_enabled:
                        queue_page_navigation(st.session_state, "company_scorecard")
                    st.rerun()
        else:
            if project.company_strategy_enabled:
                st.success("行业分析、未来趋势与内部行业底稿已完成，可以进入Company Scorecard。")
                if st.button("进入 Company Scorecard", type="primary", width="stretch"):
                    queue_page_navigation(st.session_state, "company_scorecard")
                    st.rerun()
            else:
                _render_report(project)

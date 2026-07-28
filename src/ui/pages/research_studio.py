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
    upsert_enterprise_entry,
)
from src.services.company_assessment import company_scorecard_eligibility
from src.services.report_generation import ReportGenerationError
from src.services.report_export import (
    build_report_docx,
    build_report_pdf,
    project_report_context,
)
from src.services.research_planning import SOPComplianceError
from src.state.project import (
    ProjectState,
    WorkflowStatus,
    WorkspaceMode,
    rewind_to_previous_review_gate,
)
from src.state.session import ACTIVE_PAGE_KEY, set_project
from src.ui.agent_services import (
    evidence_collection_service,
    future_intelligence_service,
    industry_analysis_service,
    report_generation_service,
    research_planning_service,
)
from src.ui.components import badge, information_card, page_header, require_project


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


def _render_gate_zero(project: ProjectState) -> None:
    brief = project.research_brief_artifact
    assert brief is not None
    st.subheader("Gate 0 · 对齐AI对研究问题和市场口径的理解")
    st.caption(
        "AI已经根据你的原始Prompt生成市场描述。请修改任何不准确的定义；确认后的版本将成为检索、分析、趋势和报告的共同口径。"
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
        ambiguities = st.text_area(
            "仍需在研究中验证的口径问题（每行一项）",
            value=_to_lines([*intent.ambiguities, *market.ambiguities]),
        )
        confirmed = st.checkbox(
            "我已核对并确认上述市场定义、纳入排除范围和报告必答问题",
            key="studio_gate_zero_confirmation",
        )
        submit = st.form_submit_button(
            "确认Gate 0并开始网页研究",
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
    intent_payload.update(
        {
            "interpreted_objective": interpreted_objective,
            "must_answer_questions": _from_lines(must_answer),
            "ambiguities": _from_lines(ambiguities),
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
                ambiguities=_from_lines(ambiguities),
            ),
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
    flags = [
        ("Prompt Analysis", project.research_brief_artifact is not None),
        ("Gate 0 · Scope", bool(project.research_brief_artifact and project.research_brief_artifact.human_confirmed)),
        ("Web Research", evidence_complete),
        ("Gate 1 · Evidence", bool(evidence and evidence.human_confirmed)),
        ("Industry Analysis", project.industry_analysis_artifact is not None),
        ("Future Intelligence", project.future_intelligence_artifact is not None),
        ("Gate 2 · Content", content_confirmed),
        ("General Report", project.general_report_artifact is not None),
    ]
    if project.company_strategy_enabled:
        flags.extend(
            [
                ("Company Scorecard", bool(project.company_scorecard_artifact and project.company_scorecard_artifact.human_confirmed)),
                ("Action Plan", bool(project.action_plan_artifact and project.action_plan_artifact.human_confirmed)),
                ("Enterprise Report", project.enterprise_decision_report_artifact is not None),
            ]
        )
    return flags


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
        "高级模式沿用同一Research Brief、Research Plan、Evidence Matrix和三道审核；这里增加企业目标与一手感知数据，供后续Scorecard和Action Plan使用。"
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
        enabled = st.toggle(
            "启用企业定制分析（Company Scorecard + Action Plan）",
            value=project.company_strategy_enabled,
        )
        target_company = st.text_input("目标企业", value=project.target_company or "")
        strategy = st.text_area(
            "企业战略目标",
            value=project.company_strategy_objective or "",
            placeholder="例如：未来三年进入高增长细分市场，同时保持核心业务现金流稳定。",
            height=100,
        )
        decision = st.text_area(
            "需要支持的企业决策（可选）",
            value=project.decision_context or "",
            height=80,
        )
        save_strategy = st.form_submit_button("保存企业目标并同步后续模块", width="stretch")
    if save_strategy:
        if enabled and (not target_company.strip() or not strategy.strip()):
            st.error("启用企业定制分析时，请填写目标企业和企业战略目标。")
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
                    "decision_context": decision or None,
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
    cols[2].metric("Enterprise Sensing", "已确认" if artifact and artifact.human_confirmed else "可选/待确认")
    cols[3].metric(
        "Company Scorecard",
        "已确认" if project.company_scorecard_artifact and project.company_scorecard_artifact.human_confirmed else "待完成",
    )
    cols[4].metric(
        "Action Plan",
        "已确认" if project.action_plan_artifact and project.action_plan_artifact.human_confirmed else "待完成",
    )
    with st.expander("快速添加一条企业一手观察", expanded=False):
        st.caption("这里只接受脱敏或模拟内容；文件上传、敏感级别和逐条审核可进入完整Enterprise Sensing。")
        with st.form("studio_enterprise_quick_entry", border=True):
            observation_title = st.text_input("观察标题", placeholder="例如：渠道反馈显示客户更重视一体化交付")
            observation_content = st.text_area("一手观察内容", height=110)
            observation_owner = st.text_input("来源角色/责任人", placeholder="例如：华东区销售负责人")
            observation_relevance = st.text_area("与企业战略目标的关系", height=80)
            add_observation = st.form_submit_button("加入Enterprise Sensing待审核区", width="stretch")
        if add_observation:
            try:
                item = EnterpriseEvidenceItem(
                    title=observation_title,
                    category=EnterpriseEvidenceCategory.MANAGEMENT_EXPERT,
                    statement_type=EnterpriseStatementType.OBSERVATION,
                    content=observation_content,
                    source_owner=observation_owner,
                    strategic_relevance=observation_relevance,
                    sensitivity=EnterpriseSensitivity.REDACTED_DEMO,
                    input_method="research_studio",
                )
            except ValidationError:
                st.error("请填写标题、内容、来源角色和战略相关性。")
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
        st.session_state[ACTIVE_PAGE_KEY] = "enterprise_sensing"
        st.rerun()
    if nav_b.button("查看 Company Scorecard 条件", width="stretch"):
        st.session_state[ACTIVE_PAGE_KEY] = "company_scorecard"
        st.rerun()
    if nav_c.button("查看 Action Plan 条件", width="stretch"):
        st.session_state[ACTIVE_PAGE_KEY] = "action_plan"
        st.rerun()

    if project.company_strategy_enabled:
        reasons = company_strategy_gate_reasons(project)
        if reasons:
            st.info("通用行业报告不受影响；企业评分与行动计划仍需补充：" + "；".join(reasons))
        else:
            st.success("企业目标与一手数据资格已通过；完成行业趋势审核后即可进入Company Scorecard。")
    else:
        st.info("当前仍可完成通用行业报告。启用企业定制分析后，企业输入才会进入Scorecard和Action Plan。")


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
        gap_acknowledged = st.checkbox(
            "我已阅读上述缺口及处理方式，并确认可以在这些证据边界下继续研究",
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

        truth_confirmed = st.checkbox(
            "我已检查拟采用证据的来源、原文和适用范围，并确认其可用于本次研究",
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
            with st.spinner("正在逐题检查原始Prompt覆盖情况并组织报告…"):
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
    cols[3].metric("Prompt覆盖", f"{answered}/{len(report.prompt_coverage)}")
    if report.unresolved_prompt_questions:
        st.warning(
            "以下原始问题仍存在部分覆盖或证据缺口："
            + "；".join(report.unresolved_prompt_questions)
        )
    with st.expander("预览完整报告", expanded=True):
        st.markdown(report.markdown)
    safe_name = "-".join(project.project_name.split()) or "industry-report"
    export_context = project_report_context(
        project,
        title=report.title,
        markdown=report.markdown,
        report_status="经人工审核的通用行业研究报告",
        generated_at=report.generated_at,
    )
    word_report = build_report_docx(export_context)
    pdf_report = build_report_pdf(export_context)
    col_a, col_b = st.columns(2)
    col_a.download_button(
        "下载 Word 报告",
        data=word_report,
        file_name=f"{safe_name}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        width="stretch",
        type="primary",
    )
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
                st.session_state[ACTIVE_PAGE_KEY] = "enterprise_sensing"
                st.rerun()
        elif st.button("进入 Company Scorecard", type="primary", width="stretch"):
            st.session_state[ACTIVE_PAGE_KEY] = "company_scorecard"
            st.rerun()


def render(project: ProjectState | None) -> None:
    page_header(
        "Research Studio · Three Human Gates",
        "行业研究工作台",
        "通用报告与高级分析师模式可以相互切换，且已经完成的研究部分不会丢失",
    )
    if not require_project(project):
        return
    assert project is not None

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
        st.info("高级工作台已启用：通用研究主流程不会改变；企业目标与一手数据在同一页面联动Scorecard和Action Plan。")
        _render_advanced_context(project)
    else:
        st.info("快速通用报告：依次确认市场口径、网页证据和报告内容，其他步骤自动衔接。")

    _render_progress(project)
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
            if st.button("生成通用行业报告", type="primary", width="stretch"):
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
                    st.rerun()
        else:
            _render_report(project)

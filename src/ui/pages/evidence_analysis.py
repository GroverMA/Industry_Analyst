"""Real evidence collection, QA, and human-review workspace."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import streamlit as st
from pydantic import ValidationError

from src.config import ConfigurationError, Settings
from src.models.analysis import AnalysisReviewStatus
from src.models.evidence import EvidenceReviewStatus, SourceTier
from src.providers.base import ProviderError
from src.services.evidence_collection import (
    EvidenceCollectionError,
    evidence_gate_reasons,
    review_evidence,
    upsert_task_run,
)
from src.services.industry_analysis import (
    IndustryAnalysisError,
    analysis_gate_reasons,
    review_analysis_finding,
)
from src.state.project import ProjectState, WorkflowStatus
from src.state.session import ACTIVE_PAGE_KEY, set_project
from src.ui.agent_services import evidence_collection_service, industry_analysis_service
from src.ui.components import (
    badge,
    information_card,
    page_header,
    render_methodology_trace,
    require_project,
)


STATUS_LABELS = {
    EvidenceReviewStatus.NEEDS_REVIEW: "待人工审核",
    EvidenceReviewStatus.ACCEPTED: "已接受",
    EvidenceReviewStatus.REJECTED: "已驳回",
    EvidenceReviewStatus.CONFLICTED: "存在冲突",
    EvidenceReviewStatus.OUT_OF_SCOPE: "超出边界",
    EvidenceReviewStatus.LOW_RELIABILITY: "低可靠性",
    EvidenceReviewStatus.UNSUPPORTED: "原文无法支持",
}

KIND_LABELS = {
    "fact": "事实",
    "data": "数据",
    "viewpoint": "来源观点",
    "inference": "分析推断",
    "forecast": "来源预测",
}

FINDING_TYPE_LABELS = {
    "fact_synthesis": "事实综合",
    "source_viewpoint": "来源观点",
    "analyst_inference": "分析师推断",
    "commercial_judgment": "商业判断",
}

ANALYSIS_STATUS_LABELS = {
    AnalysisReviewStatus.NEEDS_REVIEW: "待人工审核",
    AnalysisReviewStatus.ACCEPTED: "已接受",
    AnalysisReviewStatus.REJECTED: "已驳回",
}


def _save_artifact(project: ProjectState, artifact, *, running: bool = False) -> None:
    statuses = dict(project.workflow_status)
    statuses["evidence_collection"] = (
        WorkflowStatus.IN_PROGRESS if running else WorkflowStatus.NEEDS_REVIEW
    )
    statuses["evidence_qa"] = (
        WorkflowStatus.NOT_STARTED if running else WorkflowStatus.NEEDS_REVIEW
    )
    updated = project.model_copy(
        update={
            "evidence_collection_artifact": artifact,
            "industry_analysis_artifact": None,
            "future_intelligence_artifact": None,
            "general_report_artifact": None,
            "workflow_status": statuses,
            "current_step": "evidence_collection" if running else "evidence_qa",
            "updated_at": datetime.now(UTC),
        }
    )
    set_project(st.session_state, updated)


def _run_task(project: ProjectState, task_id: str, query_override: str | None = None):
    assert project.research_plan_artifact is not None
    return asyncio.run(
        evidence_collection_service().collect_task(
            project,
            project.research_plan_artifact,
            task_id,
            query_override=query_override,
        )
    )


def _source_table(run) -> list[dict]:
    return [
        {
            "等级": source.source_tier.value,
            "来源": source.title,
            "域名": source.domain,
            "检索通道": source.transport.upper(),
            "正文": "已抓取" if source.crawled else "仅候选",
            "搜索相关度": source.search_score,
            "网址": source.url,
        }
        for source in run.sources
    ]


def _render_evidence_item(project: ProjectState, run, item) -> None:
    artifact = project.evidence_collection_artifact
    assert artifact is not None
    source = next(source for source in run.sources if source.source_id == item.source_id)
    with st.container(border=True):
        header = st.columns([1.3, 1, 1])
        header[0].markdown(f"**{KIND_LABELS[item.kind.value]} · {STATUS_LABELS[item.review_status]}**")
        header[1].caption(f"来源等级 {source.source_tier.value} · QA {item.qa_score}/100")
        header[2].caption(f"模型置信度 {item.model_confidence:.0%}")
        st.write(item.statement)
        st.caption(f"适用范围：{item.geographic_scope} · {item.market_scope}")
        st.markdown(f"> {item.supporting_excerpt}")
        st.markdown(f"来源：[打开原网页]({source.url}) · {source.title}")
        if item.qa_flags:
            st.caption("自动质检：" + "；".join(item.qa_flags))
        if item.reviewer_note:
            st.caption("审核备注：" + item.reviewer_note)

        note = st.text_input(
            "审核备注（可选）",
            value=item.reviewer_note or "",
            key=f"note-{item.evidence_id}",
            placeholder="记录接受或驳回的理由，便于后续追责。",
        )
        accept_col, reject_col, _ = st.columns([1, 1, 2])
        if accept_col.button(
            "接受为已核验证据",
            type="primary" if item.review_status != EvidenceReviewStatus.ACCEPTED else "secondary",
            key=f"accept-{item.evidence_id}",
            disabled=item.review_status == EvidenceReviewStatus.ACCEPTED,
            width="stretch",
        ):
            override_statuses = {
                EvidenceReviewStatus.CONFLICTED,
                EvidenceReviewStatus.OUT_OF_SCOPE,
                EvidenceReviewStatus.LOW_RELIABILITY,
                EvidenceReviewStatus.UNSUPPORTED,
            }
            if item.review_status in override_statuses and not note.strip():
                st.error("该证据存在自动质检风险；如仍要接受，请先填写人工覆盖理由。")
            else:
                reviewed = review_evidence(
                    artifact,
                    item.evidence_id,
                    EvidenceReviewStatus.ACCEPTED,
                    note,
                )
                _save_artifact(project, reviewed)
                st.rerun()
        if reject_col.button(
            "驳回",
            key=f"reject-{item.evidence_id}",
            disabled=item.review_status == EvidenceReviewStatus.REJECTED,
            width="stretch",
        ):
            reviewed = review_evidence(
                artifact,
                item.evidence_id,
                EvidenceReviewStatus.REJECTED,
                note,
            )
            _save_artifact(project, reviewed)
            st.rerun()


def _save_analysis(project: ProjectState, analysis) -> None:
    statuses = dict(project.workflow_status)
    statuses["industry_analysis"] = WorkflowStatus.NEEDS_REVIEW
    statuses["future_intelligence"] = WorkflowStatus.NOT_STARTED
    updated = project.model_copy(
        update={
            "industry_analysis_artifact": analysis,
            "future_intelligence_artifact": None,
            "general_report_artifact": None,
            "workflow_status": statuses,
            "current_step": "industry_analysis",
            "updated_at": datetime.now(UTC),
        }
    )
    set_project(st.session_state, updated)


def _render_analysis_finding(project: ProjectState, finding, evidence_artifact) -> None:
    analysis = project.industry_analysis_artifact
    assert analysis is not None
    evidence_map = {item.evidence_id: item for item in evidence_artifact.evidence}
    source_map = {source.source_id: source for source in evidence_artifact.sources}
    with st.container(border=True):
        columns = st.columns([1.3, 1, 1])
        columns[0].markdown(
            f"**{FINDING_TYPE_LABELS[finding.finding_type.value]} · "
            f"{ANALYSIS_STATUS_LABELS[finding.review_status]}**"
        )
        columns[1].caption(f"分析对象：{finding.subject}")
        columns[2].caption(f"置信度：{finding.confidence:.0%}")
        st.write(finding.statement)
        st.markdown("**解释机制**")
        st.write(finding.mechanism)
        if finding.comparison_dimensions:
            st.markdown("**分析维度**")
            dimension_columns = st.columns(min(len(finding.comparison_dimensions), 3))
            for index, (key, value) in enumerate(finding.comparison_dimensions.items()):
                dimension_columns[index % len(dimension_columns)].caption(f"{key}: {value}")
        st.caption(f"适用范围：{finding.scope}")
        st.caption(f"不确定性：{finding.uncertainty}")
        st.caption(f"失效或边界条件：{finding.boundary_condition}")
        st.markdown("**Evidence Links**")
        for evidence_id in finding.evidence_ids:
            item = evidence_map[evidence_id]
            source = source_map[item.source_id]
            st.markdown(
                f"- `{evidence_id}` · [{source.title}]({source.url}) · "
                f"来源等级 {source.source_tier.value} · QA {item.qa_score}"
            )
        if finding.counter_evidence_ids:
            st.markdown("**反证或挑战证据**")
            for evidence_id in finding.counter_evidence_ids:
                item = evidence_map[evidence_id]
                source = source_map[item.source_id]
                st.markdown(f"- `{evidence_id}` · [{source.title}]({source.url})")
        if finding.reviewer_note:
            st.caption("审核备注：" + finding.reviewer_note)
        note = st.text_input(
            "判断审核备注（可选）",
            value=finding.reviewer_note or "",
            key=f"analysis-note-{finding.finding_id}",
            placeholder="记录接受或驳回这一行业判断的理由。",
        )
        accept_col, reject_col, _ = st.columns([1, 1, 2])
        if accept_col.button(
            "接受行业判断",
            type="primary" if finding.review_status != AnalysisReviewStatus.ACCEPTED else "secondary",
            disabled=finding.review_status == AnalysisReviewStatus.ACCEPTED,
            width="stretch",
            key=f"analysis-accept-{finding.finding_id}",
        ):
            reviewed = review_analysis_finding(
                analysis,
                finding.finding_id,
                AnalysisReviewStatus.ACCEPTED,
                note,
            )
            _save_analysis(project, reviewed)
            st.rerun()
        if reject_col.button(
            "驳回行业判断",
            disabled=finding.review_status == AnalysisReviewStatus.REJECTED,
            width="stretch",
            key=f"analysis-reject-{finding.finding_id}",
        ):
            reviewed = review_analysis_finding(
                analysis,
                finding.finding_id,
                AnalysisReviewStatus.REJECTED,
                note,
            )
            _save_analysis(project, reviewed)
            st.rerun()


def render(project: ProjectState | None) -> None:
    page_header(
        "04 · Evidence & Analysis",
        "把网页线索变成可核验证据",
        "按照已批准的研究计划真实搜索与抓取网页，区分来源、事实、观点、推断和预测；通过自动质检与人工审核后，证据才能进入后续行业分析。",
    )
    if not require_project(project):
        return
    assert project is not None

    plan = project.research_plan_artifact
    if plan is None or (
        not plan.human_confirmed and project.execution_authorized_at is None
    ):
        st.warning("请先在 Research Workflow 生成并批准研究计划。未经批准不会启动网页搜索。")
        if st.button("前往 Research Workflow", type="primary"):
            st.session_state[ACTIVE_PAGE_KEY] = "workflow"
            st.rerun()
        return

    try:
        settings = Settings.load()
        configured = True
        route = settings.search_transport.upper()
    except ConfigurationError:
        configured = False
        route = "NOT CONFIGURED"

    artifact = project.evidence_collection_artifact
    if artifact is not None and artifact.research_plan_id != plan.artifact_id:
        st.warning("研究计划已经变化，旧证据矩阵不会继续使用。请重新执行检索。")
        artifact = None

    accepted = (
        sum(item.review_status == EvidenceReviewStatus.ACCEPTED for item in artifact.evidence)
        if artifact
        else 0
    )
    cols = st.columns(4)
    with cols[0]:
        information_card(
            "Real API",
            "Modelhub + Agenthub，不使用模拟搜索结果。",
            value="Ready" if configured else "Needs Setup",
        )
    with cols[1]:
        information_card("Search Router", "MCP优先，结构化REST自动降级。", value=route)
    with cols[2]:
        information_card(
            "Evidence Coverage",
            "已执行任务 / 研究计划任务",
            value=f"{len(artifact.task_runs) if artifact else 0} / {len(plan.tasks)}",
        )
    with cols[3]:
        information_card("Verified Evidence", "由用户明确接受的证据。", value=str(accepted))

    with st.expander("查看来源等级与调用预算", expanded=False):
        st.markdown(
            """
            - **A**：政府、监管、交易所、正式统计与法定披露
            - **B**：学术、协会、标准、专利与正式国际机构
            - **C**：专业媒体、咨询研究、企业官网及可信行业平台
            - **D**：聚合、百科、自媒体或责任主体不清晰的二手来源

            默认每项任务最多运行 2 条搜索式，每条保留前 5 个结果，并抓取 2 个高价值且尽量不同域名的网页。相同网址在当前服务进程内使用抓取缓存。
            """
        )

    st.subheader("A. 执行证据检索")
    task_labels = [f"{task.task_id} · {task.title}" for task in plan.tasks]
    selected_label = st.selectbox("选择研究任务", task_labels)
    selected_task = plan.tasks[task_labels.index(selected_label)]
    existing_run = artifact.run_for(selected_task.task_id) if artifact else None
    if existing_run:
        st.caption("该任务已有证据；再次执行会用新结果替换该任务，其他任务不受影响。")
    custom_query = st.text_input(
        "补充检索式（可选）",
        placeholder="留空时使用Research Plan中的前两条搜索式；填写后只执行这一条补充检索式。",
    )
    run_one, run_all = st.columns(2)
    run_one_clicked = run_one.button(
        "检索所选任务" if not existing_run else "重新检索所选任务",
        type="primary",
        width="stretch",
        disabled=not configured,
    )
    run_all_clicked = run_all.button(
        "运行全部未检索任务",
        width="stretch",
        disabled=not configured,
    )

    if run_one_clicked:
        try:
            with st.spinner("正在搜索、筛选来源、抓取正文并抽取候选证据…"):
                run = _run_task(project, selected_task.task_id, custom_query or None)
                artifact = upsert_task_run(artifact, plan.artifact_id, run)
        except ValidationError:
            st.error("证据结果未能安全写入当前项目。请直接重试；已保存的其他任务不会丢失。")
        except (
            ConfigurationError,
            ProviderError,
            EvidenceCollectionError,
        ) as exc:
            st.error(f"证据检索失败：{exc}")
        else:
            _save_artifact(project, artifact)
            st.rerun()

    if run_all_clicked:
        pending = [
            task for task in plan.tasks if artifact is None or artifact.run_for(task.task_id) is None
        ]
        if not pending:
            st.info("全部研究任务都已有证据运行记录。可选择单项重新检索。")
        else:
            progress = st.progress(0, text="准备执行证据检索…")
            failures: list[str] = []
            current = artifact
            for index, task in enumerate(pending, start=1):
                progress.progress(
                    (index - 1) / len(pending),
                    text=f"正在执行 {task.task_id} · {task.title}",
                )
                try:
                    run = _run_task(project, task.task_id)
                    current = upsert_task_run(current, plan.artifact_id, run)
                except ValidationError:
                    failures.append(f"{task.task_id}：结果保存失败，请重试该任务")
                except (
                    ConfigurationError,
                    ProviderError,
                    EvidenceCollectionError,
                ) as exc:
                    failures.append(f"{task.task_id}：{exc}")
            progress.progress(1.0, text="证据检索已完成")
            if current is not None:
                _save_artifact(project, current)
            if failures:
                st.warning("部分任务未完成：\n\n" + "\n\n".join(failures))
            else:
                st.success("全部待检索任务已完成。")
            st.rerun()

    if artifact is None or not artifact.task_runs:
        st.info("尚未执行证据检索。你可以先运行一个任务快速验证，也可以运行全部未检索任务。")
        return

    st.divider()
    st.subheader("B. Candidate Sources & Evidence QA")
    st.caption("候选来源和模型抽取都不是最终事实。请打开原网页核对，并对每条证据作出接受或驳回。")
    run_map = {run.task_id: run for run in artifact.task_runs}
    for task in plan.tasks:
        run = run_map.get(task.task_id)
        if run is None:
            continue
        accepted_in_task = sum(
            item.review_status == EvidenceReviewStatus.ACCEPTED for item in run.evidence
        )
        with st.expander(
            f"{run.task_id} · {run.task_title} · {len(run.sources)}个来源 / "
            f"{len(run.evidence)}条候选 / {accepted_in_task}条已接受",
            expanded=len(artifact.task_runs) == 1,
        ):
            st.markdown("**执行的搜索式**")
            for query in run.queries_used:
                st.code(query, language=None)
            if run.sources:
                st.markdown("**Candidate Sources**")
                st.dataframe(
                    _source_table(run),
                    width="stretch",
                    hide_index=True,
                    column_config={"网址": st.column_config.LinkColumn("网址")},
                )
            if run.search_errors:
                st.warning("；".join(run.search_errors))
            if run.conflicts:
                st.markdown("**证据冲突**")
                for conflict in run.conflicts:
                    st.warning(conflict.description)
            if run.information_gaps:
                st.markdown("**信息缺口**")
                for gap in run.information_gaps:
                    st.write(f"- {gap}")
            if not run.evidence:
                st.info("本次没有形成可审阅证据；来源仍保留为线索，请调整搜索式或补充企业输入。")
            for item in run.evidence:
                _render_evidence_item(project, run, item)

    st.divider()
    st.subheader("C. Evidence Matrix & Human Gate")
    matrix = []
    for run in artifact.task_runs:
        source_map = {source.source_id: source for source in run.sources}
        for item in run.evidence:
            source = source_map[item.source_id]
            matrix.append(
                {
                    "任务": item.task_id,
                    "类型": KIND_LABELS[item.kind.value],
                    "证据陈述": item.statement,
                    "来源等级": source.source_tier.value,
                    "QA": item.qa_score,
                    "状态": STATUS_LABELS[item.review_status],
                    "来源": source.url,
                }
            )
    if matrix:
        st.dataframe(
            matrix,
            width="stretch",
            hide_index=True,
            column_config={"来源": st.column_config.LinkColumn("来源")},
        )

    reasons = evidence_gate_reasons(artifact, plan)
    if reasons:
        st.warning("证据阶段门尚未通过：\n\n" + "\n\n".join(f"- {reason}" for reason in reasons))
    elif artifact.human_confirmed:
        st.success("证据矩阵已经人工批准，可以进入Industry Analysis。")
    elif st.button(
        "批准证据矩阵并进入行业分析",
        type="primary",
        width="stretch",
    ):
        approved = artifact.model_copy(
            update={"human_confirmed": True, "updated_at": datetime.now(UTC)}
        )
        statuses = dict(project.workflow_status)
        statuses["evidence_collection"] = WorkflowStatus.COMPLETED
        statuses["evidence_qa"] = WorkflowStatus.COMPLETED
        statuses["industry_analysis"] = WorkflowStatus.READY
        updated = project.model_copy(
            update={
                "evidence_collection_artifact": approved,
                "workflow_status": statuses,
                "current_step": "industry_analysis",
                "updated_at": datetime.now(UTC),
            }
        )
        set_project(st.session_state, updated)
        st.rerun()

    if not artifact.human_confirmed:
        st.info("行业分析将在Evidence Matrix通过人工阶段门后开放。当前页面不会提前生成无证据结论。")
        return

    st.divider()
    st.subheader("D. Industry Analysis · 当前行业分析")
    st.caption(
        "本阶段只分析当前市场、价值链、竞争关系、驱动与制约、商业逻辑；未来趋势、情景预测和Action Plan将在后续独立阶段生成。"
    )
    analysis = project.industry_analysis_artifact
    if analysis is not None and analysis.evidence_collection_id != artifact.artifact_id:
        st.warning("Evidence Matrix已经变化，旧行业分析不会继续使用。请重新生成。")
        analysis = None

    generate_label = "重新生成行业分析" if analysis else "AI 生成行业分析"
    if st.button(generate_label, type="primary", width="stretch"):
        try:
            with st.spinner("正在只使用已接受证据分析市场结构、竞争关系和商业逻辑…"):
                generated = industry_analysis_service().generate(project, artifact)
        except (
            ConfigurationError,
            ProviderError,
            IndustryAnalysisError,
            ValidationError,
        ) as exc:
            st.error(f"Industry Analysis生成失败：{exc}")
        else:
            _save_analysis(project, generated)
            st.rerun()

    if analysis is None:
        st.info("点击“AI 生成行业分析”。模型只能读取本项目中人工接受的Evidence ID。")
        return

    render_methodology_trace(analysis.methodology)
    summary_columns = st.columns(4)
    summary_columns[0].metric("使用证据", len(analysis.input_evidence_ids))
    summary_columns[1].metric("分析模块", len(analysis.modules))
    summary_columns[2].metric("行业判断", len(analysis.findings))
    summary_columns[3].metric(
        "已接受判断",
        sum(
            finding.review_status == AnalysisReviewStatus.ACCEPTED
            for finding in analysis.findings
        ),
    )

    for module in analysis.modules:
        accepted_findings = sum(
            item.review_status == AnalysisReviewStatus.ACCEPTED
            for item in module.findings
        )
        with st.expander(
            f"{module.title} · {len(module.findings)}项判断 / {accepted_findings}项已接受",
            expanded=module.module_id == "market_value_chain",
        ):
            st.write(module.executive_summary)
            if module.evidence_gaps:
                st.markdown("**证据缺口**")
                for gap in module.evidence_gaps:
                    st.write(f"- {gap}")
            if module.rejected_questions:
                st.markdown("**当前证据无法回答**")
                for question in module.rejected_questions:
                    st.write(f"- {question}")
            if not module.findings:
                st.info("本模块未形成证据充分的行业判断，系统保留为空并显示缺口。")
            for finding in module.findings:
                _render_analysis_finding(project, finding, artifact)

    if analysis.company_implications:
        with st.expander(
            f"目标企业初步影响 · {len(analysis.company_implications)}项",
            expanded=False,
        ):
            st.warning("这里只记录与当前行业证据直接相关的初步影响，不构成公司评分或行动建议。")
            for finding in analysis.company_implications:
                _render_analysis_finding(project, finding, artifact)

    if analysis.cross_module_conflicts:
        st.markdown("#### 跨模块冲突")
        for conflict in analysis.cross_module_conflicts:
            st.warning(conflict)
    if analysis.overall_evidence_limitations:
        st.markdown("#### 整体证据边界")
        for limitation in analysis.overall_evidence_limitations:
            st.write(f"- {limitation}")

    analysis_reasons = analysis_gate_reasons(analysis)
    if analysis_reasons:
        st.warning(
            "行业分析阶段门尚未通过：\n\n"
            + "\n\n".join(f"- {reason}" for reason in analysis_reasons)
        )
    elif analysis.human_confirmed:
        st.success("当前行业分析已经人工批准；未来发展趋势预测将在下一阶段进行。")
    elif st.button(
        "批准当前行业分析并进入趋势预测准备",
        type="primary",
        width="stretch",
    ):
        approved_analysis = analysis.model_copy(
            update={"human_confirmed": True, "updated_at": datetime.now(UTC)}
        )
        statuses = dict(project.workflow_status)
        statuses["industry_analysis"] = WorkflowStatus.COMPLETED
        statuses["future_intelligence"] = WorkflowStatus.READY
        updated = project.model_copy(
            update={
                "industry_analysis_artifact": approved_analysis,
                "workflow_status": statuses,
                "current_step": "future_intelligence",
                "updated_at": datetime.now(UTC),
            }
        )
        set_project(st.session_state, updated)
        st.rerun()

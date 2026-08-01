"""Evidence-grounded Future Intelligence workspace."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st
from pydantic import ValidationError

from src.config import ConfigurationError
from src.models.future import ForecastReviewStatus, ScenarioType
from src.providers.base import ProviderError
from src.services.enterprise_sensing import company_strategy_gate_reasons
from src.services.future_intelligence import (
    FutureIntelligenceError,
    forecast_gate_reasons,
    review_forecast_item,
)
from src.state.project import ProjectState, WorkflowStatus
from src.state.session import queue_page_navigation, set_project
from src.ui.agent_services import future_intelligence_service
from src.ui.components import (
    information_card,
    page_header,
    render_methodology_trace,
    require_project,
)


CATEGORY_LABELS = {
    "technology_product": "技术与产品",
    "competitive_landscape": "竞争格局",
    "business_model": "商业模式",
    "customer_demand": "客户需求",
    "policy_capital_value_chain": "政策、资本与产业链",
    "cross_cutting": "跨因素综合趋势",
}

REVIEW_LABELS = {
    ForecastReviewStatus.NEEDS_REVIEW: "待人工审核",
    ForecastReviewStatus.ACCEPTED: "已接受",
    ForecastReviewStatus.REJECTED: "已驳回",
}

SCENARIO_LABELS = {
    ScenarioType.BASELINE: "基准情景",
    ScenarioType.ACCELERATED: "加速情景",
    ScenarioType.BLOCKED: "受阻情景",
}


def _save_future(project: ProjectState, artifact) -> None:
    statuses = dict(project.workflow_status)
    statuses["future_intelligence"] = WorkflowStatus.NEEDS_REVIEW
    statuses["company_assessment"] = (
        WorkflowStatus.NOT_STARTED
        if project.company_strategy_enabled
        else WorkflowStatus.NOT_APPLICABLE
    )
    updated = project.model_copy(
        update={
            "future_intelligence_artifact": artifact,
            "general_report_artifact": None,
            "workflow_status": statuses,
            "current_step": "future_intelligence",
            "updated_at": datetime.now(UTC),
        }
    )
    set_project(st.session_state, updated)


def _evidence_links(project: ProjectState, evidence_ids: list[str]) -> None:
    artifact = project.evidence_collection_artifact
    assert artifact is not None
    evidence_map = {item.evidence_id: item for item in artifact.evidence}
    source_map = {source.source_id: source for source in artifact.sources}
    for evidence_id in evidence_ids:
        item = evidence_map[evidence_id]
        source = source_map[item.source_id]
        st.markdown(
            f"- `{evidence_id}` · [{source.title}]({source.url}) · "
            f"质量评分 {item.qa_score}"
        )


def _render_review_controls(project: ProjectState, item, item_id: str, label: str) -> None:
    artifact = project.future_intelligence_artifact
    assert artifact is not None
    if item.reviewer_note:
        st.caption("审核备注：" + item.reviewer_note)
    note = st.text_input(
        f"{label}审核备注（可选）",
        value=item.reviewer_note or "",
        key=f"forecast-note-{item_id}",
        placeholder="记录接受或驳回的理由。",
    )
    accept_col, reject_col, _ = st.columns([1, 1, 2])
    if accept_col.button(
        f"接受{label}",
        type="primary" if item.review_status != ForecastReviewStatus.ACCEPTED else "secondary",
        disabled=item.review_status == ForecastReviewStatus.ACCEPTED,
        key=f"forecast-accept-{item_id}",
        width="stretch",
    ):
        reviewed = review_forecast_item(
            artifact,
            item_id,
            ForecastReviewStatus.ACCEPTED,
            note,
        )
        _save_future(project, reviewed)
        st.rerun()
    if reject_col.button(
        f"驳回{label}",
        disabled=item.review_status == ForecastReviewStatus.REJECTED,
        key=f"forecast-reject-{item_id}",
        width="stretch",
    ):
        reviewed = review_forecast_item(
            artifact,
            item_id,
            ForecastReviewStatus.REJECTED,
            note,
        )
        _save_future(project, reviewed)
        st.rerun()


def _render_trend(project: ProjectState, trend) -> None:
    with st.container(border=True):
        header = st.columns([1.5, 1, 1])
        header[0].markdown(f"#### {trend.title}")
        header[1].caption(
            f"{CATEGORY_LABELS[trend.category.value]} · {trend.forecast_horizon}"
        )
        header[2].caption(
            f"{REVIEW_LABELS[trend.review_status]} · 置信度 {trend.confidence.overall}/100"
        )
        st.write(trend.forecast_statement)
        st.progress(trend.confidence.overall / 100)
        score_columns = st.columns(4)
        scores = (
            ("证据质量", trend.confidence.evidence_quality),
            ("来源多样性", trend.confidence.source_diversity),
            ("信号一致性", trend.confidence.signal_consistency),
            ("因果完整度", trend.confidence.causal_clarity),
            ("玩家投入", trend.confidence.player_commitment),
            ("时间距离", trend.confidence.time_distance),
            ("反证韧性", trend.confidence.counter_evidence_resilience),
            (
                "企业信号",
                trend.confidence.enterprise_signal_support
                if trend.confidence.enterprise_signal_support is not None
                else "未接入",
            ),
        )
        for index, (name, value) in enumerate(scores):
            score_columns[index % 4].metric(name, value)
        st.caption("置信度说明：" + trend.confidence_note)

        st.markdown("**Observed Signals**")
        for signal in trend.observed_signals:
            actor = f" · {signal.actor}" if signal.actor else ""
            date = f" · {signal.signal_date}" if signal.signal_date else ""
            st.write(f"- {signal.description}{actor}{date} · {signal.direction}")
        st.markdown("**Causal Mechanism**")
        st.write(" → ".join(trend.causal_mechanism))
        st.markdown("**关键假设**")
        for assumption in trend.assumptions:
            st.write(f"- {assumption}")

        if trend.player_moves:
            st.markdown("**Player Move Signals**")
            st.dataframe(
                [
                    {
                        "参与者": move.player,
                        "状态": move.move_status.value,
                        "当前信号": move.current_signal,
                        "可能下一步": move.inferred_next_move,
                        "依据": move.rationale,
                        "不确定性": move.uncertainty,
                    }
                    for move in trend.player_moves
                ],
                hide_index=True,
                width="stretch",
            )

        impact_columns = st.columns(3)
        impact_columns[0].markdown("**竞争格局影响**")
        impact_columns[0].write(trend.competition_impact)
        impact_columns[1].markdown("**商业模式影响**")
        impact_columns[1].write(trend.business_model_impact)
        impact_columns[2].markdown("**客户需求影响**")
        impact_columns[2].write(trend.customer_demand_impact)
        if trend.company_exposure:
            st.warning("目标企业潜在影响：" + trend.company_exposure)

        st.markdown("**Leading Indicators**")
        st.dataframe(
            [
                {
                    "指标": indicator.name,
                    "定义": indicator.definition,
                    "观察方向": indicator.direction_to_watch,
                    "触发条件": indicator.trigger_condition,
                    "数据来源": indicator.data_source,
                    "频率": indicator.monitoring_frequency,
                }
                for indicator in trend.leading_indicators
            ],
            hide_index=True,
            width="stretch",
        )
        falsification_col, uncertainty_col = st.columns(2)
        with falsification_col:
            st.markdown("**Falsification Conditions**")
            for condition in trend.falsification_conditions:
                st.write(f"- {condition}")
        with uncertainty_col:
            st.markdown("**关键不确定性**")
            for uncertainty in trend.uncertainties:
                st.write(f"- {uncertainty}")
        st.markdown("**Evidence Links**")
        _evidence_links(project, trend.evidence_ids)
        st.caption("Industry Finding IDs: " + "、".join(trend.finding_ids))
        if trend.counter_evidence_ids:
            st.markdown("**Counter-evidence**")
            _evidence_links(project, trend.counter_evidence_ids)
        _render_review_controls(project, trend, trend.trend_id, "趋势")


def _render_scenario(project: ProjectState, scenario) -> None:
    with st.container(border=True):
        st.caption(
            f"{SCENARIO_LABELS[scenario.scenario_type]} · "
            f"定性可能性 {scenario.likelihood_label} · {REVIEW_LABELS[scenario.review_status]}"
        )
        st.markdown(f"#### {scenario.title}")
        st.write(scenario.narrative)
        st.markdown("**触发条件**")
        for condition in scenario.trigger_conditions:
            st.write(f"- {condition}")
        st.markdown("**可能结果**")
        for outcome in scenario.expected_outcomes:
            st.write(f"- {outcome}")
        st.markdown("**领先指标**")
        for indicator in scenario.leading_indicators:
            st.write(f"- {indicator}")
        st.markdown("**失效条件**")
        for condition in scenario.falsification_conditions:
            st.write(f"- {condition}")
        st.caption("Trend IDs: " + "、".join(scenario.trend_ids))
        _render_review_controls(project, scenario, scenario.scenario_id, "情景")


def render(project: ProjectState | None) -> None:
    page_header(
        "05 · Trend Forecast",
        "用可证伪的逻辑推演未来",
        "从已批准行业分析和已观察信号出发，解释竞争格局、商业模式、客户需求与玩家行动可能如何变化，并持续记录领先指标和可能推翻预测的条件。",
    )
    if not require_project(project):
        return
    assert project is not None

    evidence = project.evidence_collection_artifact
    analysis = project.industry_analysis_artifact
    if evidence is None or analysis is None or (
        not analysis.human_confirmed and project.future_intelligence_artifact is None
    ):
        st.warning("请先完成Evidence Matrix与当前Industry Analysis的人工审核。未来预测不能绕过当前事实和判断阶段。")
        if st.button("前往 Evidence & Analysis", type="primary"):
            queue_page_navigation(st.session_state, "evidence_analysis")
            st.rerun()
        return

    artifact = project.future_intelligence_artifact
    if artifact is not None and (
        artifact.industry_analysis_id != analysis.artifact_id
        or artifact.evidence_collection_id != evidence.artifact_id
    ):
        st.warning("证据或当前行业分析已经变化，旧趋势预测不会继续使用。请重新生成。")
        artifact = None

    summary = st.columns(4)
    with summary[0]:
        information_card("Forecast Mode", "企业一手信号未接入时仍可运行。", value="General")
    with summary[1]:
        information_card("Trend Radar", "有证据基础的未来变化假设。", value=str(len(artifact.trends) if artifact else 0))
    with summary[2]:
        information_card("Scenarios", "基准、加速与受阻三种情景。", value=str(len(artifact.scenarios) if artifact else 0))
    with summary[3]:
        accepted_count = (
            sum(item.review_status == ForecastReviewStatus.ACCEPTED for item in artifact.trends)
            if artifact
            else 0
        )
        information_card("Accepted Trends", "经过人工确认的趋势。", value=str(accepted_count))

    generate_label = "重新生成 Future Intelligence" if artifact else "AI 生成 Future Intelligence"
    if st.button(generate_label, type="primary", width="stretch"):
        try:
            with st.spinner("正在推演趋势、玩家行动、三种情景与可证伪指标…"):
                generated = future_intelligence_service().generate(project, evidence, analysis)
        except (
            ConfigurationError,
            ProviderError,
            FutureIntelligenceError,
            ValidationError,
        ) as exc:
            st.error(f"Future Intelligence生成失败：{exc}")
        else:
            _save_future(project, generated)
            st.rerun()

    if artifact is None:
        st.info("点击生成后，系统只会使用已接受Evidence与已接受Industry Finding，不会把通用模型知识当成预测证据。")
        return

    render_methodology_trace(artifact.methodology)
    method = artifact.forecast_methodology
    method_labels = {
        "causal_scenario": "因果情景法",
        "naive_baseline": "朴素基准",
        "exponential_smoothing": "指数平滑",
        "trend_regression": "趋势回归",
        "regularized_driver_regression": "正则化驱动变量回归",
    }
    with st.container(border=True):
        st.markdown("#### 预测方法门")
        method_cols = st.columns(3)
        method_cols[0].metric("本轮方法", method_labels[method.selected_method.value])
        method_cols[1].metric("同口径观测", method.structured_observation_count)
        method_cols[2].metric(
            "量化模型",
            "已运行" if method.quantitative_forecast_used else "未满足数据门槛",
        )
        st.write(method.selection_rationale)
        st.caption(method.validation_design + " " + method.prediction_interval)
    if artifact.forecast_mode == "general":
        st.info("当前为General Forecast。未接入企业渠道、客户、销售或专家一手信号，企业信号支持度不会被虚构评分。")

    st.subheader("A. Forecast Overview & Trend Radar")
    average_confidence = round(sum(item.confidence.overall for item in artifact.trends) / len(artifact.trends))
    overview = st.columns(3)
    overview[0].metric("趋势数量", len(artifact.trends))
    overview[1].metric("平均系统置信度", f"{average_confidence}/100")
    overview[2].metric("监测重点", len(artifact.monitoring_priorities))
    st.dataframe(
        [
            {
                "趋势": trend.title,
                "类别": CATEGORY_LABELS[trend.category.value],
                "时间范围": trend.forecast_horizon,
                "置信度": trend.confidence.overall,
                "状态": REVIEW_LABELS[trend.review_status],
            }
            for trend in artifact.trends
        ],
        hide_index=True,
        width="stretch",
    )
    for trend in artifact.trends:
        _render_trend(project, trend)

    st.divider()
    st.subheader("B. Scenario Comparison")
    st.caption("情景使用定性可能性，不伪装成未经统计验证的精确概率。")
    scenario_columns = st.columns(3)
    ordered = sorted(
        artifact.scenarios,
        key=lambda item: {
            ScenarioType.BASELINE: 0,
            ScenarioType.ACCELERATED: 1,
            ScenarioType.BLOCKED: 2,
        }[item.scenario_type],
    )
    for column, scenario in zip(scenario_columns, ordered):
        with column:
            _render_scenario(project, scenario)

    st.divider()
    st.subheader("C. Monitoring & Forecast Gaps")
    monitoring_col, gaps_col = st.columns(2)
    with monitoring_col:
        st.markdown("**Monitoring Priorities**")
        for priority in artifact.monitoring_priorities:
            st.write(f"- {priority}")
    with gaps_col:
        st.markdown("**Forecast Gaps**")
        if artifact.forecast_gaps:
            for gap in artifact.forecast_gaps:
                st.write(f"- {gap}")
        else:
            st.write("当前未记录额外预测缺口。")

    reasons = forecast_gate_reasons(artifact)
    if reasons:
        st.warning("趋势预测阶段门尚未通过：\n\n" + "\n\n".join(f"- {reason}" for reason in reasons))
    elif artifact.human_confirmed:
        if not project.company_strategy_enabled:
            st.success("Future Intelligence已经人工批准。当前为通用路径，可继续生成General Report。")
        elif company_strategy_gate_reasons(project):
            st.success("Future Intelligence已经人工批准。完善Enterprise Sensing后可进入Company Scorecard。")
        else:
            st.success("Future Intelligence已经人工批准，可以进入Company Scorecard。")
    elif st.button(
        "批准趋势与情景并进入公司评分准备",
        type="primary",
        width="stretch",
    ):
        approved = artifact.model_copy(
            update={"human_confirmed": True, "updated_at": datetime.now(UTC)}
        )
        statuses = dict(project.workflow_status)
        statuses["future_intelligence"] = WorkflowStatus.COMPLETED
        strategy_reasons = company_strategy_gate_reasons(project)
        if not project.company_strategy_enabled:
            statuses["company_assessment"] = WorkflowStatus.NOT_APPLICABLE
            statuses["action_plan"] = WorkflowStatus.NOT_APPLICABLE
            statuses["human_review"] = WorkflowStatus.READY
            next_step = "human_review"
        elif not strategy_reasons:
            statuses["company_assessment"] = WorkflowStatus.READY
            next_step = "company_assessment"
        else:
            statuses["company_assessment"] = WorkflowStatus.NOT_STARTED
            next_step = "company_assessment"
        updated = project.model_copy(
            update={
                "future_intelligence_artifact": approved,
                "workflow_status": statuses,
                "current_step": next_step,
                "updated_at": datetime.now(UTC),
            }
        )
        set_project(st.session_state, updated)
        st.rerun()

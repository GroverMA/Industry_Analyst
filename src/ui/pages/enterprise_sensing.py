"""Enterprise sensing inputs and company-strategy eligibility gate."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st
from pydantic import ValidationError

from src.models.enterprise import (
    EnterpriseDataDimension,
    EnterpriseEvidenceCategory,
    EnterpriseEvidenceItem,
    EnterpriseReviewStatus,
    EnterpriseSensitivity,
    EnterpriseStatementType,
)
from src.services.enterprise_sensing import (
    EnterpriseSensingError,
    company_strategy_gate_reasons,
    confirm_enterprise_artifact,
    enterprise_item_from_upload,
    load_redacted_demo_enterprise_pack,
    new_enterprise_artifact,
    review_enterprise_entry,
    upsert_enterprise_entry,
)
from src.state.project import ProjectState, WorkflowStatus
from src.state.session import queue_page_navigation, set_project
from src.state.user_role import UserRole, get_user_role
from src.ui.components import badge, information_card, page_header, require_project


CATEGORY_LABELS = {
    EnterpriseEvidenceCategory.STRATEGIC_INTENT: "战略意图与管理层约束",
    EnterpriseEvidenceCategory.INTERNAL_DOCUMENT: "内部文件",
    EnterpriseEvidenceCategory.SALES_CHANNEL: "销售与渠道",
    EnterpriseEvidenceCategory.CUSTOMER: "客户需求与反馈",
    EnterpriseEvidenceCategory.PRODUCT: "产品与服务",
    EnterpriseEvidenceCategory.OPERATIONS: "运营与供应链",
    EnterpriseEvidenceCategory.FINANCE: "财务与单位经济性",
    EnterpriseEvidenceCategory.RESEARCH_DEVELOPMENT: "研发与技术",
    EnterpriseEvidenceCategory.ORGANIZATION_RESOURCES: "组织与资源",
    EnterpriseEvidenceCategory.MANAGEMENT_EXPERT: "管理层或专家判断",
    EnterpriseEvidenceCategory.SELF_DIAGNOSIS: "企业自我诊断",
}

DATA_DIMENSION_LABELS = {
    EnterpriseDataDimension.SELL_IN: "Sell-in／渠道进货",
    EnterpriseDataDimension.SELL_OUT: "Sell-out／终端销售",
    EnterpriseDataDimension.CUSTOMER_PENETRATION: "客户覆盖与渗透率",
    EnterpriseDataDimension.INVENTORY: "库存与周转",
    EnterpriseDataDimension.PRICE_MARGIN: "价格、折扣与毛利",
    EnterpriseDataDimension.CHANNEL_COVERAGE: "渠道覆盖与质量",
    EnterpriseDataDimension.PRODUCT_PORTFOLIO: "产品组合与生命周期",
    EnterpriseDataDimension.OPERATIONS_SUPPLY: "运营、产能与供应链",
    EnterpriseDataDimension.FINANCIAL_RESOURCE: "财务表现与资源投入",
    EnterpriseDataDimension.ORGANIZATION_CAPABILITY: "组织与能力建设",
    EnterpriseDataDimension.OTHER: "其他企业数据",
}

STATEMENT_LABELS = {
    EnterpriseStatementType.FACT: "可核验内部事实",
    EnterpriseStatementType.OBSERVATION: "一手观察",
    EnterpriseStatementType.VIEWPOINT: "内部观点",
    EnterpriseStatementType.HYPOTHESIS: "待验证假设",
    EnterpriseStatementType.STRATEGIC_INTENT: "战略意图",
    EnterpriseStatementType.MIXED_DOCUMENT: "混合型文件",
}

SENSITIVITY_LABELS = {
    EnterpriseSensitivity.REDACTED_DEMO: "脱敏/模拟（适合公开演示）",
    EnterpriseSensitivity.INTERNAL: "内部资料",
    EnterpriseSensitivity.CONFIDENTIAL: "机密（公开版不可确认）",
    EnterpriseSensitivity.RESTRICTED: "受限（公开版不可确认）",
}


def _save_artifact(project: ProjectState, artifact) -> None:
    statuses = dict(project.workflow_status)
    statuses["company_assessment"] = (
        WorkflowStatus.NOT_STARTED
        if project.company_strategy_enabled
        else WorkflowStatus.NOT_APPLICABLE
    )
    statuses["action_plan"] = (
        WorkflowStatus.NOT_STARTED
        if project.company_strategy_enabled
        else WorkflowStatus.NOT_APPLICABLE
    )
    statuses["decision_report"] = WorkflowStatus.NOT_STARTED
    updated = project.model_copy(
        update={
            "enterprise_sensing_artifact": artifact,
            "company_scorecard_artifact": None,
            "action_plan_artifact": None,
            "enterprise_decision_report_artifact": None,
            "workflow_status": statuses,
            "updated_at": datetime.now(UTC),
        }
    )
    set_project(st.session_state, updated)


def render(project: ProjectState | None) -> None:
    page_header(
        "03 · Enterprise Sensing",
        "接入企业的一手感知系统",
        "企业战略研究必须先接入并确认一手企业资料，之后才进入行业研究、公司评分与行动计划。",
    )
    if not require_project(project):
        return
    assert project is not None

    information_card(
        "企业战略研究",
        "目标企业 + 战略意图 + 已确认企业资料，才可开始后续行业研究并进入公司评分与Action Plan。",
        value="Enterprise Strategy Path",
    )

    if project.company_strategy_enabled:
        st.markdown(
            badge("Company Strategy Path", accent=True)
            + badge(project.target_company or "Missing Company")
            + badge("Strategic Intent Required"),
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            st.markdown("#### 已锁定的企业战略意图")
            st.write(project.company_strategy_objective)
            st.caption("Action Plan必须逐项回扣此目标；修改目标后，Enterprise Sensing确认会失效。")
    else:
        st.info(
            "当前是通用行业研究路径。你仍可试用本模块，但Company Scorecard与Action Plan保持锁定。"
            "如需启用，请在Research Studio高级分析师工作台填写目标企业与企业战略意图。"
        )

    artifact = project.enterprise_sensing_artifact or new_enterprise_artifact(project)

    with st.container(border=True):
        st.markdown("#### 开放式企业知识接口 · 演示入口")
        st.write(
            "企业可以接入销售、客户、产品、研发、运营、财务和管理层观察。"
            "如果暂时没有真实企业资料，可加载一组明确标记为模拟的数据，体验Scorecard与Action Plan完整链路。"
        )
        if st.button("加载脱敏模拟企业资料包", width="stretch"):
            demo_artifact = load_redacted_demo_enterprise_pack(project, artifact)
            _save_artifact(project, demo_artifact)
            st.rerun()

    st.subheader("A. 企业自我诊断问题")
    st.caption(
        "请提交企业认为实现战略意图时最需要改进或验证的方面。系统会把这些内容视为管理假设，"
        "并在后续行业分析、Company Scorecard和Action Plan中结合证据进行验证，而不会直接当作事实。"
    )
    with st.form("enterprise_self_diagnosis", border=True):
        diagnosis_area = st.text_input(
            "最需要改进或验证的方面",
            placeholder="例如：重点医院客户渗透率偏低，现有渠道无法支持高端产品进入",
        )
        current_symptoms = st.text_area(
            "当前表现、症状或已观察到的问题",
            placeholder="描述目前发生了什么、影响了哪些客户或业务环节；公开演示只填写脱敏或模拟内容。",
            height=120,
        )
        strategic_relevance = st.text_area(
            "为什么会影响企业战略意图",
            placeholder="说明该问题支持、限制或挑战了哪一项战略选择。",
            height=90,
        )
        attempted_actions = st.text_area(
            "已经尝试的措施（可选）",
            placeholder="例如：调整经销商激励、增加重点客户联合拜访，但转化率改善有限。",
            height=80,
        )
        ai_validation_question = st.text_area(
            "希望AI重点验证的问题（可选）",
            placeholder="例如：问题主要来自渠道能力、产品价值主张，还是客户准入周期？",
            height=80,
        )
        col_c, col_d = st.columns(2)
        source_owner = col_c.text_input("提交部门／责任人", placeholder="例如：商业运营负责人")
        observed_at = col_d.date_input("诊断日期")
        sensitivity = st.selectbox(
            "敏感级别",
            list(EnterpriseSensitivity),
            format_func=SENSITIVITY_LABELS.get,
        )
        add_diagnosis = st.form_submit_button("提交企业诊断假设", type="primary", width="stretch")
        if add_diagnosis:
            content = "\n".join(
                part for part in [
                    f"当前表现：{current_symptoms.strip()}" if current_symptoms.strip() else "",
                    f"已尝试措施：{attempted_actions.strip()}" if attempted_actions.strip() else "",
                    f"希望重点验证：{ai_validation_question.strip()}" if ai_validation_question.strip() else "",
                ] if part
            )
            try:
                item = EnterpriseEvidenceItem(
                    title=diagnosis_area,
                    category=EnterpriseEvidenceCategory.SELF_DIAGNOSIS,
                    statement_type=EnterpriseStatementType.HYPOTHESIS,
                    content=content,
                    source_owner=source_owner,
                    observed_at=observed_at.isoformat(),
                    strategic_relevance=strategic_relevance,
                    sensitivity=sensitivity,
                    input_method="self_diagnosis",
                )
                artifact = upsert_enterprise_entry(artifact, project, item)
            except ValidationError:
                st.error("请填写改进方面、当前表现、提交部门／责任人及其与战略意图的关系。")
            else:
                _save_artifact(project, artifact)
                st.rerun()

    st.subheader("B. 分层上传脱敏企业文件")
    st.caption(
        "可一次上传同一数据层面的多个文件，并可重复新增不同批次，例如Sell-in、Sell-out、客户渗透率、"
        "库存、价格与毛利。支持DOCX、XLSX、PPTX、PDF、TXT、Markdown和CSV；单文件不超过5MB。"
    )
    with st.form("enterprise_file_entry", border=True):
        uploaded_files = st.file_uploader(
            "选择一个或多个文件",
            type=["txt", "md", "csv", "pdf", "docx", "xlsx", "pptx"],
            accept_multiple_files=True,
        )
        col_dimension, col_period = st.columns(2)
        data_dimension = col_dimension.selectbox(
            "本批资料的数据层面",
            list(EnterpriseDataDimension),
            format_func=DATA_DIMENSION_LABELS.get,
        )
        reporting_period = col_period.text_input(
            "数据期间（可选）",
            placeholder="例如：2026Q1、2025全年",
        )
        file_owner = st.text_input("文件来源角色/责任人", placeholder="例如：产品负责人")
        file_relevance = st.text_area(
            "与企业战略意图的关系",
            placeholder="例如：用于判断现有产品能力能否支持目标细分市场。",
            height=80,
        )
        file_sensitivity = st.selectbox(
            "文件敏感级别",
            list(EnterpriseSensitivity),
            format_func=SENSITIVITY_LABELS.get,
            key="enterprise_file_sensitivity",
        )
        add_file = st.form_submit_button("提取文字并加入待审核资料", width="stretch")
        if add_file:
            if not uploaded_files:
                st.error("请先选择至少一个文件。")
            else:
                failures = []
                added = 0
                for uploaded in uploaded_files:
                    try:
                        item = enterprise_item_from_upload(
                            file_name=uploaded.name,
                            mime_type=uploaded.type,
                            data=uploaded.getvalue(),
                            source_owner=file_owner,
                            strategic_relevance=file_relevance,
                            sensitivity=file_sensitivity,
                            data_dimension=data_dimension,
                            reporting_period=reporting_period,
                        )
                        artifact = upsert_enterprise_entry(artifact, project, item)
                        added += 1
                    except (EnterpriseSensingError, ValidationError) as exc:
                        failures.append(f"{uploaded.name}：{exc}")
                if added:
                    _save_artifact(project, artifact)
                    st.success(f"已加入{added}个文件；可继续上传其他数据层面的资料。")
                if failures:
                    st.error("以下文件接入失败：" + "；".join(failures))

    st.subheader("C. 人工审核企业资料")
    if not artifact.entries:
        st.info("尚未添加企业资料。通用行业研究可以直接跳过本页。")
    elif any(item.review_status == EnterpriseReviewStatus.NEEDS_REVIEW for item in artifact.entries):
        if st.button("批量接受全部脱敏/模拟资料", type="primary", width="stretch"):
            reviewed = artifact
            for item in artifact.entries:
                if (
                    item.review_status == EnterpriseReviewStatus.NEEDS_REVIEW
                    and item.sensitivity == EnterpriseSensitivity.REDACTED_DEMO
                ):
                    reviewed = review_enterprise_entry(
                        reviewed,
                        item.enterprise_evidence_id,
                        EnterpriseReviewStatus.ACCEPTED,
                        "用户批量确认脱敏/模拟企业资料",
                    )
            _save_artifact(project, reviewed)
            st.rerun()
    for item in artifact.entries:
        status_label = item.review_status.value.replace("_", " ").title()
        with st.expander(f"{item.enterprise_evidence_id} · {item.title} · {status_label}"):
            st.markdown(
                badge(CATEGORY_LABELS[item.category])
                + badge(STATEMENT_LABELS[item.statement_type])
                + badge(SENSITIVITY_LABELS[item.sensitivity]),
                unsafe_allow_html=True,
            )
            st.caption(
                f"来源：{item.source_owner} · 日期：{item.observed_at or '未提供'} · 输入：{item.input_method}"
            )
            if item.data_dimension:
                st.caption(
                    "数据层面："
                    + DATA_DIMENSION_LABELS[item.data_dimension]
                    + (f" · 期间：{item.reporting_period}" if item.reporting_period else "")
                )
            st.write("**战略相关性：** " + item.strategic_relevance)
            preview = item.content[:1500] + ("…" if len(item.content) > 1500 else "")
            st.text_area(
                "内容预览",
                value=preview,
                height=150,
                disabled=True,
                key=f"enterprise_preview_{item.enterprise_evidence_id}",
            )
            note = st.text_input(
                "审核备注（拒绝时建议说明原因）",
                value=item.reviewer_note or "",
                key=f"enterprise_note_{item.enterprise_evidence_id}",
            )
            col_accept, col_reject = st.columns(2)
            if col_accept.button(
                "接受为企业证据",
                type="primary",
                key=f"accept_{item.enterprise_evidence_id}",
                width="stretch",
            ):
                reviewed = review_enterprise_entry(
                    artifact,
                    item.enterprise_evidence_id,
                    EnterpriseReviewStatus.ACCEPTED,
                    note,
                )
                _save_artifact(project, reviewed)
                st.rerun()
            if col_reject.button(
                "拒绝",
                key=f"reject_{item.enterprise_evidence_id}",
                width="stretch",
            ):
                reviewed = review_enterprise_entry(
                    artifact,
                    item.enterprise_evidence_id,
                    EnterpriseReviewStatus.REJECTED,
                    note,
                )
                _save_artifact(project, reviewed)
                st.rerun()

    st.subheader("D. 权限确认与战略路径资格")
    with st.container(border=True):
        consent = st.checkbox(
            "我允许比赛提供的模型服务在当前项目中处理已接受的脱敏/模拟企业资料",
            value=artifact.consent_to_model_processing,
        )
        demo_ack = st.checkbox(
            "我确认公开演示版不包含真实机密或受限数据",
            value=artifact.public_demo_acknowledged,
        )
        if st.button("确认 Enterprise Sensing", type="primary", width="stretch"):
            try:
                confirmed = confirm_enterprise_artifact(
                    artifact,
                    project,
                    consent_to_model_processing=consent,
                    public_demo_acknowledged=demo_ack,
                )
            except EnterpriseSensingError as exc:
                st.error(str(exc))
            else:
                statuses = dict(project.workflow_status)
                future_ready = bool(
                    project.future_intelligence_artifact
                    and project.future_intelligence_artifact.human_confirmed
                )
                statuses["company_assessment"] = (
                    WorkflowStatus.READY if future_ready else WorkflowStatus.NOT_STARTED
                )
                statuses["action_plan"] = WorkflowStatus.NOT_STARTED
                statuses["decision_report"] = WorkflowStatus.NOT_STARTED
                updated = project.model_copy(
                    update={
                        "enterprise_sensing_artifact": confirmed,
                        "company_scorecard_artifact": None,
                        "action_plan_artifact": None,
                        "enterprise_decision_report_artifact": None,
                        "workflow_status": statuses,
                        "updated_at": datetime.now(UTC),
                    }
                )
                set_project(st.session_state, updated)
                st.rerun()

    current = project.model_copy(update={"enterprise_sensing_artifact": artifact})
    reasons = company_strategy_gate_reasons(current)
    if not reasons:
        reviewer_mode = get_user_role(st.session_state) == UserRole.REVIEWER
        st.success(
            "企业资料已确认，可以返回报告审阅工作台生成完整企业报告。"
            if reviewer_mode
            else "企业战略资格已通过。趋势与情景批准后，可进入Company Scorecard。"
        )
        if st.button(
            "返回报告审阅工作台" if reviewer_mode else "前往 Company Scorecard",
            width="stretch",
            type="primary" if reviewer_mode else "secondary",
        ):
            queue_page_navigation(
                st.session_state,
                "research_studio" if reviewer_mode else "company_scorecard",
            )
            st.rerun()
    else:
        st.warning("Company Scorecard / Action Plan仍锁定：\n\n" + "\n\n".join(f"- {reason}" for reason in reasons))

    st.warning("公开演示版只能使用脱敏或模拟资料。真实企业机密需要私有部署、权限控制和审计能力。")

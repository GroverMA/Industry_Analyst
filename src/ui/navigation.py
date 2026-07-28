"""Project history and workspace navigation for the Streamlit shell."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from uuid import uuid4

import streamlit as st

from src.state.browser_history import (
    HISTORY_RESPONSE_KEY,
    project_node_label,
    project_progress,
    queue_history_command,
)
from src.state.project import ProjectState
from src.state.project import rewind_to_previous_review_gate
from src.state.session import (
    ACTIVE_PAGE_KEY,
    clear_project,
    queue_page_navigation,
    set_project,
)


@dataclass(frozen=True, slots=True)
class PageDefinition:
    key: str
    label: str
    short_label: str


PAGES = (
    PageDefinition("home", "Project Home", "项目首页"),
    PageDefinition("research_studio", "Research Studio", "研究主流程"),
    PageDefinition("research_brief", "Research Brief", "研究简报"),
    PageDefinition("workflow", "Research Workflow", "研究流程"),
    PageDefinition("enterprise_sensing", "Enterprise Sensing", "企业感知"),
    PageDefinition("evidence_analysis", "Evidence & Analysis", "证据与分析"),
    PageDefinition("trend_forecast", "Trend Forecast", "趋势预测"),
    PageDefinition("company_scorecard", "Company Scorecard", "公司评分"),
    PageDefinition("action_plan", "Action Plan", "行动计划"),
    PageDefinition("decision_report", "Decision Report", "决策报告"),
)


def _open_history_project(row: dict) -> None:
    queue_history_command(
        st.session_state,
        "load",
        project_id=str(row.get("project_id") or ""),
    )
    st.rerun()


def _run_history_action(
    command_type: str,
    project_id: str,
    *,
    active_project_id: str | None,
) -> None:
    queue_history_command(
        st.session_state,
        command_type,
        project_id=project_id,
    )
    if project_id == active_project_id and command_type in {"finish", "delete"}:
        clear_project(st.session_state)
    st.rerun()


def _render_history_actions(
    row: dict,
    *,
    active_project_id: str | None,
    key_prefix: str,
) -> None:
    """Render a compact, row-level replacement for a native context menu.

    Streamlit does not expose a reliable right-click event for sidebar rows.
    A discoverable ellipsis popover keeps the actions attached to the project
    without adding a full ``项目管理`` section after every record.
    """

    project_id = str(row.get("project_id") or "")
    lifecycle = str(row.get("lifecycle_state") or "active")
    status_group = str(row.get("status_group") or "in_progress")
    is_in_progress = lifecycle == "active" and status_group == "in_progress"
    with st.popover(
        "⋯",
        key=f"{key_prefix}_actions_{project_id}",
        help="项目操作",
        width="stretch",
    ):
        if is_in_progress and st.button(
            "终止研究",
            key=f"{key_prefix}_finish_{project_id}",
            width="stretch",
        ):
            _run_history_action(
                "finish", project_id, active_project_id=active_project_id
            )
        delete_confirmed = st.checkbox(
            "确认删除此项目及其全部研究记录",
            key=f"{key_prefix}_delete_confirm_{project_id}",
        )
        if st.button(
            "删除项目",
            key=f"{key_prefix}_delete_{project_id}",
            width="stretch",
            disabled=not delete_confirmed,
        ):
            _run_history_action(
                "delete", project_id, active_project_id=active_project_id
            )


def _history_row(
    row: dict,
    *,
    active_project_id: str | None,
    key_prefix: str = "history",
) -> None:
    project_id = str(row.get("project_id") or "")
    name = str(row.get("project_name") or "未命名研究")
    progress = int(row.get("progress") or 0)
    node = str(row.get("node_label") or "Research Brief")
    is_active = project_id == active_project_id
    label = f"{name}{' · 当前' if is_active else ''}"
    project_col, action_col = st.columns(
        [0.84, 0.16], gap="small", vertical_alignment="top"
    )
    with project_col:
        if st.button(
            label,
            key=f"{key_prefix}_open_{project_id}",
            width="stretch",
            disabled=not project_id,
        ):
            _open_history_project(row)
        st.caption(f"{progress}% · {node}")
    with action_col:
        _render_history_actions(
            row,
            active_project_id=active_project_id,
            key_prefix=key_prefix,
        )


def _filtered_projects(catalog: dict, search_text: str) -> list[dict]:
    rows = catalog.get("projects") or []
    needle = search_text.strip().casefold()
    if not needle:
        return list(rows)
    return [
        row
        for row in rows
        if needle
        in " ".join(
            str(row.get(field) or "")
            for field in ("project_name", "industry", "region", "node_label")
        ).casefold()
    ]


def _render_history(catalog: dict, project: ProjectState | None) -> None:
    response_message = st.session_state.pop(HISTORY_RESPONSE_KEY, None)
    if response_message:
        st.warning(response_message)

    search_text = st.text_input(
        "搜索研究项目",
        placeholder="搜索项目",
        label_visibility="collapsed",
        key="history_search",
    )
    rows = _filtered_projects(catalog, search_text)
    active_id = project.project_id if project else None
    in_progress = [row for row in rows if row.get("status_group") == "in_progress"]
    historical = [
        row
        for row in rows
        if row.get("status_group") in {"completed", "archived"}
    ]

    st.markdown('<div class="ia-sidebar-section">进行中的项目</div>', unsafe_allow_html=True)
    if in_progress:
        for row in in_progress:
            _history_row(row, active_project_id=active_id)
    else:
        st.caption("暂无进行中的项目")

    st.markdown('<div class="ia-sidebar-section">历史研究项目</div>', unsafe_allow_html=True)
    if historical:
        for row in historical:
            _history_row(row, active_project_id=active_id, key_prefix="historical")
    else:
        st.caption("暂无已完成项目")


def _render_project_organizer(catalog: dict, project: ProjectState | None) -> None:
    rows = list(catalog.get("projects") or [])
    folders = list(catalog.get("folders") or [])
    with st.expander("项目文件夹与分类", expanded=False):
        with st.form("create_history_folder", border=False):
            folder_name = st.text_input("新建文件夹", placeholder="例如：医疗健康")
            create = st.form_submit_button("创建文件夹", width="stretch")
            if create:
                if not folder_name.strip():
                    st.error("请输入文件夹名称。")
                else:
                    queue_history_command(
                        st.session_state,
                        "create_folder",
                        folder_id=uuid4().hex,
                        name=folder_name.strip(),
                    )
                    st.rerun()

        if folders:
            folder_names = {str(item["folder_id"]): str(item["name"]) for item in folders}
            for folder_id, folder_name in folder_names.items():
                folder_rows = [row for row in rows if row.get("folder_id") == folder_id]
                st.markdown(f"**{escape(folder_name)} · {len(folder_rows)} 个项目**")
                if folder_rows:
                    for row in folder_rows:
                        _history_row(
                            row,
                            active_project_id=project.project_id if project else None,
                            key_prefix=f"folder_{folder_id}",
                        )
                else:
                    st.caption("该文件夹尚无项目")

        if rows:
            project_labels = {
                str(row.get("project_id")): str(row.get("project_name") or "未命名研究")
                for row in rows
                if row.get("project_id")
            }
            folder_labels = {"": "未分类"}
            folder_labels.update(
                {
                    str(item.get("folder_id")): str(item.get("name") or "未命名文件夹")
                    for item in folders
                    if item.get("folder_id")
                }
            )
            with st.form("move_history_project", border=False):
                selected_project = st.selectbox(
                    "选择项目",
                    list(project_labels),
                    format_func=project_labels.get,
                )
                current_folder = next(
                    (
                        str(row.get("folder_id") or "")
                        for row in rows
                        if str(row.get("project_id")) == selected_project
                    ),
                    "",
                )
                folder_keys = list(folder_labels)
                folder_index = folder_keys.index(current_folder) if current_folder in folder_keys else 0
                selected_folder = st.selectbox(
                    "归档到",
                    folder_keys,
                    index=folder_index,
                    format_func=folder_labels.get,
                )
                move = st.form_submit_button("保存分类", width="stretch")
                if move:
                    queue_history_command(
                        st.session_state,
                        "move",
                        project_id=selected_project,
                        folder_id=selected_folder or None,
                    )
                    st.rerun()


def _render_workspace_navigation(project: ProjectState) -> str:
    st.markdown('<div class="ia-sidebar-section">当前项目工作台</div>', unsafe_allow_html=True)
    keys = [page.key for page in PAGES]
    labels = {page.key: f"{page.label} · {page.short_label}" for page in PAGES}
    current = st.session_state.get(ACTIVE_PAGE_KEY, "research_studio")
    if current not in keys:
        st.session_state[ACTIVE_PAGE_KEY] = "research_studio"
    selected = st.selectbox(
        "当前项目页面",
        keys,
        format_func=labels.get,
        label_visibility="collapsed",
        key=ACTIVE_PAGE_KEY,
    )
    rewind = rewind_to_previous_review_gate(project)
    with st.expander("流程控制", expanded=False):
        if rewind is None:
            st.caption("当前已经处于最早可编辑节点。")
        else:
            _, message = rewind
            st.caption(message)
            confirmed = st.checkbox(
                "确认返回并使后续旧结果失效",
                key=f"rewind_confirm_{project.project_id}_{project.current_step}",
            )
            if st.button(
                "返回上一研究节点",
                width="stretch",
                disabled=not confirmed,
                key=f"rewind_{project.project_id}_{project.current_step}",
            ):
                updated, notice = rewind
                set_project(st.session_state, updated)
                st.session_state[HISTORY_RESPONSE_KEY] = notice
                queue_page_navigation(st.session_state, "research_studio")
                st.rerun()
    return selected


def render_sidebar(project: ProjectState | None, catalog: dict) -> str:
    with st.sidebar:
        st.markdown(
            """
            <div class="ia-brand">
              <div class="ia-brand-name">Industry Analyst OS</div>
              <div class="ia-brand-sub">Evidence-first research workspace</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("新建研究", type="primary", width="stretch", key="new_research_sidebar"):
            clear_project(st.session_state)
            st.rerun()

        if project:
            progress = project_progress(project)
            st.markdown(
                f"""
                <div class="ia-sidebar-project">
                  <strong>{escape(project.project_name)}</strong><br/>
                  <span>{escape(project.industry)} · {escape(project.region)}</span>
                  <div class="ia-project-meta">{progress}% · {escape(project_node_label(project))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.progress(progress / 100)

        _render_history(catalog, project)
        _render_project_organizer(catalog, project)

        selected = "home"
        if project:
            selected = _render_workspace_navigation(project)
        else:
            st.session_state[ACTIVE_PAGE_KEY] = "home"

        st.divider()
        st.caption("项目内容保存在当前浏览器中，不写入共享服务器。")
        st.caption("Stage 7B · Strategy-to-Action Studio")
    return selected

"""Industry Analyst OS Streamlit entry point."""

from __future__ import annotations

import importlib
import inspect

import streamlit as st

from pydantic import ValidationError

from src.state.browser_history import (
    HISTORY_CATALOG_KEY,
    HISTORY_COMMAND_KEY,
    HISTORY_RESPONSE_KEY,
    VALID_HISTORY_PAGES,
    normalize_catalog,
    render_history_bridge,
    resume_page_for_project,
)
from src.state.project import ProjectState
from src.state.session import (
    ACTIVE_PAGE_KEY,
    NAVIGATION_REQUEST_KEY,
    get_project,
    initialize_session,
    set_project,
)
from src.ui.components import render_project_strip
import src.ui.navigation as navigation
from src.ui.pages import PAGE_RENDERERS
from src.ui.theme import apply_theme


st.set_page_config(
    page_title="Industry Analyst OS",
    page_icon="📊",
    layout="wide",
    # Desktop keeps the project library visible; Streamlit collapses it on
    # narrow/mobile viewports so the research form remains immediately usable.
    initial_sidebar_state="auto",
)
apply_theme()
initialize_session(st.session_state)

project = get_project(st.session_state)
history_response = render_history_bridge(
    project=project,
    active_page=st.session_state.get(ACTIVE_PAGE_KEY, "home"),
    command=st.session_state.get(HISTORY_COMMAND_KEY),
)
if history_response:
    st.session_state[HISTORY_CATALOG_KEY] = normalize_catalog(history_response)
    request_id = history_response.get("request_id")
    command = st.session_state.get(HISTORY_COMMAND_KEY)
    if command and request_id == command.get("request_id"):
        if command.get("type") == "load" and history_response.get("loaded_project"):
            try:
                restored = ProjectState.model_validate(history_response["loaded_project"])
            except ValidationError:
                st.session_state[HISTORY_RESPONSE_KEY] = "该历史项目已损坏，无法恢复。"
            else:
                set_project(st.session_state, restored)
                loaded_page = history_response.get("loaded_active_page")
                st.session_state[ACTIVE_PAGE_KEY] = resume_page_for_project(
                    restored,
                    loaded_page if loaded_page in VALID_HISTORY_PAGES else None,
                )
        if history_response.get("error"):
            st.session_state[HISTORY_RESPONSE_KEY] = "浏览器项目记录暂时不可用。"
        st.session_state.pop(HISTORY_COMMAND_KEY, None)
        st.rerun()

project = get_project(st.session_state)

requested_page = st.session_state.pop(NAVIGATION_REQUEST_KEY, None)
if requested_page in VALID_HISTORY_PAGES:
    st.session_state[ACTIVE_PAGE_KEY] = requested_page

# Streamlit Community Cloud can hot-reload ``app.py`` while retaining an older
# imported module in the running process.  The history release changed the
# sidebar contract from one argument to two, so refresh that module only when a
# stale one-argument implementation is still cached.  A normal cold start never
# enters this branch.
if len(inspect.signature(navigation.render_sidebar).parameters) < 2:
    navigation = importlib.reload(navigation)

active_page = navigation.render_sidebar(
    project,
    st.session_state.get(HISTORY_CATALOG_KEY, {"projects": [], "folders": []}),
)

render_project_strip(project)
st.write("")
PAGE_RENDERERS[active_page](project)

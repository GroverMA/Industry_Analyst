"""Industry Analyst OS Streamlit entry point."""

from __future__ import annotations

import importlib

import streamlit as st

from pydantic import ValidationError

import src.state.browser_history as browser_history
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
import src.ui.pages as pages_registry
import src.ui.theme as theme


# Streamlit may retain an older imported module while hot-reloading ``app.py``.
# Resolve the history API through the module object so a newly added helper does
# not fail during import before the app has a chance to refresh that module.
if not hasattr(browser_history, "resume_page_for_project"):
    browser_history = importlib.reload(browser_history)

HISTORY_CATALOG_KEY = browser_history.HISTORY_CATALOG_KEY
HISTORY_COMMAND_KEY = browser_history.HISTORY_COMMAND_KEY
HISTORY_RESPONSE_KEY = browser_history.HISTORY_RESPONSE_KEY
VALID_HISTORY_PAGES = browser_history.VALID_HISTORY_PAGES
normalize_catalog = browser_history.normalize_catalog
render_history_bridge = browser_history.render_history_bridge
resume_page_for_project = browser_history.resume_page_for_project


st.set_page_config(
    page_title="Industry Analyst OS",
    page_icon="📊",
    layout="wide",
    # Desktop keeps the project library visible; Streamlit collapses it on
    # narrow/mobile viewports so the research form remains immediately usable.
    initial_sidebar_state="auto",
)


RUNTIME_RELEASE_KEY = "industry_analyst_runtime_release"
RUNTIME_RELEASE_ID = "future-intelligence-controls-v1"

# Community Cloud updates the checkout without always restarting the Python
# process. Refresh the modules changed by this release once per browser session
# so an existing app instance cannot keep serving the previous navigation,
# research workflow, forecasting service, or CSS after GitHub has updated.
if st.session_state.get(RUNTIME_RELEASE_KEY) != RUNTIME_RELEASE_ID:
    navigation = importlib.reload(navigation)
    future_module = importlib.import_module("src.services.future_intelligence")
    importlib.reload(future_module)
    agent_services_module = importlib.import_module("src.ui.agent_services")
    importlib.reload(agent_services_module)
    research_studio_module = importlib.import_module("src.ui.pages.research_studio")
    research_studio_module = importlib.reload(research_studio_module)
    trend_forecast_module = importlib.import_module("src.ui.pages.trend_forecast")
    trend_forecast_module = importlib.reload(trend_forecast_module)
    pages_registry.PAGE_RENDERERS["research_studio"] = research_studio_module.render
    pages_registry.PAGE_RENDERERS["trend_forecast"] = trend_forecast_module.render
    theme = importlib.reload(theme)
    st.session_state[RUNTIME_RELEASE_KEY] = RUNTIME_RELEASE_ID

PAGE_RENDERERS = pages_registry.PAGE_RENDERERS


theme.apply_theme()
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

active_page = navigation.render_sidebar(
    project,
    st.session_state.get(HISTORY_CATALOG_KEY, {"projects": [], "folders": []}),
)

render_project_strip(project)
st.write("")
PAGE_RENDERERS[active_page](project)

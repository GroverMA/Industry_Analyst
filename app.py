"""Industry Analyst OS Streamlit entry point."""

from __future__ import annotations

import streamlit as st

from src.state.session import get_project, initialize_session
from src.ui.components import render_project_strip
from src.ui.navigation import render_sidebar
from src.ui.pages import PAGE_RENDERERS
from src.ui.theme import apply_theme


st.set_page_config(
    page_title="Industry Analyst OS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()
initialize_session(st.session_state)

project = get_project(st.session_state)
active_page = render_sidebar(project)

render_project_strip(project)
st.write("")
PAGE_RENDERERS[active_page](project)

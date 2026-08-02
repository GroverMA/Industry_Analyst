"""Shared, readable report preview for Consultant and Reviewer roles."""

from __future__ import annotations

import re

import streamlit as st


FONT_OPTIONS = {
    "专业无衬线": "Inter, 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    "报告宋体": "'Noto Serif CJK SC', 'Songti SC', SimSun, serif",
    "系统字体": "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif",
}


def _safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def render_report_preview(
    markdown: str,
    *,
    key: str,
    expanded: bool = True,
    label: str = "预览完整报告",
) -> None:
    """Render a responsive report with user-adjustable typography.

    Controls only affect the browser preview. Word and PDF retain the governed
    export template so different reviewers cannot accidentally alter the
    official delivery style.
    """

    safe_key = _safe_key(key)
    with st.expander("报告显示设置", expanded=False):
        st.caption("以下设置只改变网页预览，不修改报告内容、Word或PDF文件。")
        font_col, heading_col, body_col = st.columns(3)
        font_label = font_col.selectbox(
            "字体",
            list(FONT_OPTIONS),
            index=0,
            key=f"{safe_key}_font",
        )
        heading_color = heading_col.color_picker(
            "标题颜色",
            "#172033",
            key=f"{safe_key}_heading_color",
        )
        body_color = body_col.color_picker(
            "正文颜色",
            "#3F4A5E",
            key=f"{safe_key}_body_color",
        )
        size_cols = st.columns(5)
        h1_size = size_cols[0].slider("报告标题", 30, 52, 40, key=f"{safe_key}_h1")
        h2_size = size_cols[1].slider("一级标题", 24, 40, 31, key=f"{safe_key}_h2")
        h3_size = size_cols[2].slider("二级标题", 18, 32, 24, key=f"{safe_key}_h3")
        body_size = size_cols[3].slider("正文", 14, 23, 18, key=f"{safe_key}_body")
        line_height = size_cols[4].slider(
            "行距",
            1.4,
            2.2,
            1.85,
            step=0.05,
            key=f"{safe_key}_line",
        )

    preview_key = f"report_preview_{safe_key}"
    css_class = f"st-key-{preview_key}"
    font_family = FONT_OPTIONS[font_label]
    st.markdown(
        f"""
        <style>
        .{css_class} {{
            max-width: 980px;
            margin: 0 auto;
            padding: clamp(1.35rem, 3vw, 2.8rem);
            background: #FFFFFF;
            border: 1px solid #E4E8ED;
            border-radius: 16px;
            box-shadow: 0 12px 40px rgba(23, 32, 51, .05);
            font-family: {font_family};
        }}
        .{css_class} h1, .{css_class} h2, .{css_class} h3, .{css_class} h4 {{
            color: {heading_color} !important;
            font-family: {font_family};
            letter-spacing: -.025em;
            scroll-margin-top: 5rem;
        }}
        .{css_class} h1 {{
            font-size: {h1_size}px !important;
            line-height: 1.22 !important;
            margin: 0 0 2rem !important;
        }}
        .{css_class} h2 {{
            font-size: {h2_size}px !important;
            line-height: 1.32 !important;
            margin: 3rem 0 1.15rem !important;
            padding-top: .2rem;
        }}
        .{css_class} h3 {{
            font-size: {h3_size}px !important;
            line-height: 1.4 !important;
            margin: 2rem 0 .8rem !important;
        }}
        .{css_class} h4 {{
            font-size: {max(17, h3_size - 3)}px !important;
            line-height: 1.45 !important;
            margin: 1.55rem 0 .65rem !important;
        }}
        .{css_class} p, .{css_class} li, .{css_class} td, .{css_class} th {{
            color: {body_color} !important;
            font-family: {font_family};
            font-size: {body_size}px !important;
            line-height: {line_height} !important;
            letter-spacing: .005em;
            word-break: normal;
            overflow-wrap: anywhere;
        }}
        .{css_class} p {{
            margin: 0 0 1.15rem !important;
            text-align: justify;
            text-justify: inter-ideograph;
        }}
        .{css_class} table {{
            width: 100%;
            margin: 1.1rem 0 1.7rem;
            font-size: {max(13, body_size - 2)}px;
        }}
        .{css_class} th {{ background: #EEF5F5; color: #234D57 !important; }}
        .{css_class} a {{ color: #2563A5 !important; text-decoration-thickness: 1px; }}
        .{css_class} h1 a, .{css_class} h2 a, .{css_class} h3 a, .{css_class} h4 a,
        .{css_class} [data-testid="stHeaderActionElements"] {{
            display: none !important;
        }}
        @media (max-width: 760px) {{
            .{css_class} {{ padding: 1.15rem; border-radius: 12px; }}
            .{css_class} h1 {{ font-size: {max(28, h1_size - 7)}px !important; }}
            .{css_class} h2 {{ font-size: {max(22, h2_size - 5)}px !important; }}
            .{css_class} h3 {{ font-size: {max(18, h3_size - 3)}px !important; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.expander(label, expanded=expanded):
        with st.container(key=preview_key):
            st.markdown(markdown)


"""Central design tokens and CSS for easy later visual revision."""

from __future__ import annotations

import streamlit as st


COLORS = {
    "background": "#F8FAFB",
    "surface": "rgba(255, 255, 255, 0.88)",
    "surface_solid": "#FFFFFF",
    "text_primary": "#172033",
    "text_secondary": "#667085",
    "border": "#E4E8ED",
    "border_strong": "#D5DBE3",
    "accent": "#356B77",
    "accent_soft": "#EAF2F3",
    "success": "#2F7669",
    "warning": "#9A6A22",
    "danger": "#A84B4B",
}

RADIUS = {"small": "8px", "medium": "14px", "large": "20px"}
SHADOW = "0 10px 32px rgba(23, 32, 51, 0.045)"
MAX_WIDTH = "1260px"


def apply_theme() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --ia-bg: {COLORS['background']};
            --ia-surface: {COLORS['surface']};
            --ia-surface-solid: {COLORS['surface_solid']};
            --ia-text: {COLORS['text_primary']};
            --ia-muted: {COLORS['text_secondary']};
            --ia-border: {COLORS['border']};
            --ia-accent: {COLORS['accent']};
            --ia-accent-soft: {COLORS['accent_soft']};
            --ia-radius: {RADIUS['medium']};
        }}
        .stApp {{ background: var(--ia-bg); color: var(--ia-text); }}
        [data-testid="stHeader"] {{ background: rgba(248, 250, 251, 0.72); }}
        [data-testid="stAppDeployButton"] {{ display: none; }}
        [data-testid="stAppViewContainer"] > .main .block-container {{
            max-width: {MAX_WIDTH};
            padding-top: 2.1rem;
            padding-bottom: 4rem;
        }}
        [data-testid="stSidebar"] {{
            background: rgba(255, 255, 255, 0.92);
            border-right: 1px solid var(--ia-border);
        }}
        [data-testid="stSidebar"] .block-container {{ padding-top: 1.5rem; }}
        h1, h2, h3 {{ letter-spacing: -0.025em; color: var(--ia-text); }}
        p, label, [data-testid="stCaptionContainer"] {{ color: var(--ia-muted); }}
        div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {{
            background: var(--ia-surface);
            border-color: var(--ia-border) !important;
            border-radius: var(--ia-radius);
            box-shadow: {SHADOW};
        }}
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stSelectbox"] > div > div {{
            background: rgba(255,255,255,0.96);
            border-color: var(--ia-border);
        }}
        .stButton > button, .stFormSubmitButton > button {{
            border-radius: {RADIUS['small']};
            border: 1px solid {COLORS['border_strong']};
            box-shadow: none;
            font-weight: 600;
            min-height: 2.6rem;
        }}
        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {{
            background: var(--ia-accent);
            border-color: var(--ia-accent);
            color: white;
        }}
        .stButton > button[kind^="primary"] *,
        .stFormSubmitButton > button[kind^="primary"] * {{
            color: #FFFFFF !important;
        }}
        .stDownloadButton > button {{
            min-height: 2.6rem;
            border-radius: {RADIUS['small']};
            border: 1px solid var(--ia-accent) !important;
            background: var(--ia-accent) !important;
            color: #FFFFFF !important;
            font-weight: 650;
            box-shadow: none;
        }}
        .stDownloadButton > button *,
        .stDownloadButton > button p,
        .stDownloadButton > button span {{
            color: #FFFFFF !important;
        }}
        .stDownloadButton > button:hover,
        .stDownloadButton > button:focus,
        .stDownloadButton > button:active {{
            background: {COLORS['accent']} !important;
            border-color: {COLORS['accent']} !important;
            color: #FFFFFF !important;
        }}
        .stDownloadButton > button:hover *,
        .stDownloadButton > button:focus *,
        .stDownloadButton > button:active * {{
            color: #FFFFFF !important;
        }}
        .stButton > button[kind^="primary"]:disabled,
        .stFormSubmitButton > button[kind^="primary"]:disabled {{
            background: #6B929B;
            border-color: #6B929B;
            color: #FFFFFF;
            opacity: 1;
        }}
        .stButton > button[kind^="primary"]:disabled *,
        .stFormSubmitButton > button[kind^="primary"]:disabled * {{
            color: #FFFFFF !important;
        }}
        .stProgress > div > div > div > div {{ background: var(--ia-accent); }}
        .ia-brand {{ padding: .35rem 0 1.25rem; }}
        .ia-brand-name {{ font-size: 1.05rem; font-weight: 720; color: var(--ia-text); }}
        .ia-brand-sub {{ font-size: .72rem; color: var(--ia-muted); margin-top: .16rem; }}
        .ia-hero {{
            background: var(--ia-surface);
            border: 1px solid var(--ia-border);
            border-radius: {RADIUS['large']};
            padding: 2.4rem 2.5rem;
            box-shadow: {SHADOW};
            margin-bottom: 1.45rem;
            backdrop-filter: blur(14px);
        }}
        .ia-eyebrow {{
            font-size: .72rem; font-weight: 700; color: var(--ia-accent);
            letter-spacing: .1em; text-transform: uppercase; margin-bottom: .7rem;
        }}
        .ia-hero h1 {{ margin: 0; font-size: clamp(2rem, 3.5vw, 3rem); line-height: 1.08; }}
        .ia-hero p {{ max-width: 760px; font-size: 1.02rem; line-height: 1.75; margin: 1rem 0 0; }}
        .ia-role-hero {{
            max-width: 820px; margin: 8vh auto 2rem; text-align: center;
        }}
        .ia-role-hero h1 {{
            margin: .2rem 0 .8rem; font-size: clamp(2rem, 4vw, 3rem);
        }}
        .ia-role-hero p {{
            max-width: 680px; margin: 0 auto; line-height: 1.75;
        }}
        .ia-reviewer-banner {{
            display: flex; justify-content: space-between; gap: 1rem; align-items: center;
            border: 1px solid #CFE0E3; border-radius: 12px;
            background: #F1F7F7; padding: .85rem 1rem; margin: .55rem 0 1rem;
        }}
        .ia-reviewer-banner strong {{ color: var(--ia-text); font-size: .86rem; }}
        .ia-reviewer-banner span {{ color: var(--ia-muted); font-size: .78rem; }}
        .ia-trace-card {{
            border: 1px solid var(--ia-border); border-radius: 12px;
            background: rgba(255,255,255,.76); padding: .95rem 1rem; margin-bottom: .7rem;
        }}
        .ia-trace-card strong {{ color: var(--ia-text); }}
        .ia-page-head {{ margin-bottom: 1.35rem; }}
        .ia-page-head h1 {{ font-size: 2rem; margin: .25rem 0 .35rem; }}
        .ia-page-head p {{ margin: 0; max-width: 820px; line-height: 1.7; }}
        .ia-badge {{
            display: inline-flex; align-items: center; padding: .28rem .62rem;
            border: 1px solid var(--ia-border); border-radius: 999px;
            background: rgba(255,255,255,.78); color: var(--ia-muted);
            font-size: .72rem; font-weight: 650; margin-right: .35rem;
        }}
        .ia-badge-accent {{ background: var(--ia-accent-soft); color: var(--ia-accent); border-color: #D8E7E9; }}
        .ia-card {{
            background: var(--ia-surface); border: 1px solid var(--ia-border);
            border-radius: var(--ia-radius); padding: 1.2rem 1.25rem;
            box-shadow: {SHADOW}; height: 100%; backdrop-filter: blur(12px);
        }}
        .ia-card-title {{ color: var(--ia-text); font-weight: 680; margin-bottom: .35rem; }}
        .ia-card-copy {{ color: var(--ia-muted); font-size: .86rem; line-height: 1.6; }}
        .ia-stat {{
            border-top: 1px solid var(--ia-border); padding-top: .9rem; margin-top: .9rem;
            color: var(--ia-text); font-size: 1.35rem; font-weight: 700;
        }}
        .ia-sidebar-project {{
            border: 1px solid var(--ia-border); background: rgba(248,250,251,.72);
            border-radius: 12px; padding: .85rem; margin: .65rem 0 1rem;
        }}
        .ia-sidebar-project strong {{ color: var(--ia-text); font-size: .83rem; }}
        .ia-sidebar-project span {{ color: var(--ia-muted); font-size: .72rem; }}
        .ia-project-meta {{
            color: var(--ia-accent); font-size: .72rem; font-weight: 650;
            margin-top: .5rem;
        }}
        .ia-sidebar-section {{
            color: var(--ia-text); font-size: .72rem; font-weight: 740;
            letter-spacing: .035em; margin: 1.2rem 0 .45rem;
        }}
        [data-testid="stSidebar"] .stButton > button:not([kind^="primary"]) {{
            justify-content: flex-start;
            border-color: transparent;
            background: transparent;
            min-height: 2.2rem;
            padding-left: .55rem;
            font-weight: 560;
        }}
        [data-testid="stSidebar"] .stButton > button:not([kind^="primary"]):hover {{
            border-color: var(--ia-border);
            background: var(--ia-accent-soft);
        }}
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
            font-size: .68rem;
            margin-top: -.45rem;
            padding-left: .55rem;
        }}
        .ia-prompt-guide {{
            border: 1px solid #CFE0E3;
            border-left: 4px solid var(--ia-accent);
            border-radius: 12px;
            background: #F1F7F7;
            padding: 1rem 1.05rem;
            margin: .35rem 0 .75rem;
        }}
        .ia-prompt-guide-compact {{ padding: .85rem 1rem; }}
        .ia-prompt-kicker {{
            color: var(--ia-accent); font-size: .7rem; font-weight: 760;
            letter-spacing: .08em; text-transform: uppercase; margin-bottom: .28rem;
        }}
        .ia-prompt-title {{ color: var(--ia-text); font-weight: 720; font-size: 1rem; }}
        .ia-prompt-copy {{ color: var(--ia-muted); font-size: .82rem; line-height: 1.55; margin-top: .25rem; }}
        .ia-status-row {{
            display:flex; justify-content:space-between; align-items:center;
            border-bottom:1px solid var(--ia-border); padding:.75rem 0;
        }}
        .ia-status-row:last-child {{ border-bottom:0; }}
        .ia-pipeline-scroll {{
            overflow-x: auto; padding: .35rem .15rem .45rem; margin: .45rem 0 0;
        }}
        .ia-pipeline-track {{
            position: relative; display: grid;
            grid-template-columns: repeat(var(--ia-step-count, 11), minmax(88px, 1fr));
            min-width: 760px; align-items: end;
        }}
        .ia-pipeline-track::after {{
            content: ""; position: absolute; left: 4.5%; right: 4.5%; bottom: 13px;
            height: 2px; background: #DDE5E8; z-index: 0;
        }}
        .ia-pipeline-track::before {{
            content: ""; position: absolute; left: 4.5%; bottom: 13px;
            width: var(--ia-progress-width, 0%);
            height: 2px; background: var(--ia-accent); z-index: 1;
        }}
        .ia-pipeline-step {{
            position: relative; z-index: 1; display: flex; flex-direction: column;
            align-items: center; justify-content: flex-end; gap: .5rem;
            min-width: 88px; text-align: center;
        }}
        .ia-pipeline-step strong {{
            color: var(--ia-muted); font-size: .68rem; line-height: 1.25;
            min-height: 2.2em; display: flex; align-items: flex-end; justify-content: center;
        }}
        .ia-pipeline-step span {{
            width: 1.72rem; height: 1.72rem; border-radius: 999px;
            display: inline-flex; align-items: center; justify-content: center;
            background: #FFFFFF; border: 2px solid #CDD8DC;
            color: #596579; font-size: .7rem; font-weight: 760;
        }}
        .ia-pipeline-step-done strong {{ color: var(--ia-text); font-weight: 720; }}
        .ia-pipeline-step-done span {{
            background: var(--ia-accent); border-color: var(--ia-accent); color: #FFFFFF;
        }}
        .ia-rewind-guide {{
            display: grid; grid-template-columns: auto 1fr; gap: .2rem .7rem;
            align-items: baseline; margin: .45rem 0 .55rem; padding: .72rem .85rem;
            border: 1px solid var(--ia-border); border-radius: 10px;
            background: rgba(255, 255, 255, .72);
        }}
        .ia-rewind-guide strong {{ color: var(--ia-text); font-size: .78rem; }}
        .ia-rewind-guide span {{ color: var(--ia-muted); font-size: .76rem; line-height: 1.5; }}
        .ia-rewind-guide small {{
            grid-column: 2; color: var(--ia-accent); font-size: .7rem; line-height: 1.45;
        }}
        .ia-muted {{ color: var(--ia-muted); }}
        #MainMenu, footer {{ visibility: hidden; }}
        @media (max-width: 760px) {{
            [data-testid="stAppViewContainer"] > .main .block-container {{ padding-top: 1rem; }}
            [data-testid="stSidebar"] {{ background: #FFFFFF; }}
            .ia-hero {{ padding: 1.5rem; }}
            .ia-pipeline-track {{ min-width: 820px; }}
            .ia-rewind-guide {{ grid-template-columns: 1fr; }}
            .ia-rewind-guide small {{ grid-column: 1; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

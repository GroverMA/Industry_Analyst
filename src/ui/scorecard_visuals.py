"""Shared strategy scorecard visuals for company strategy workspaces."""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go


def scorecard_comparison_rows(scorecard) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for order, item in enumerate(scorecard.dimensions):
        company_score = getattr(item, "score", None)
        benchmark_score = getattr(item, "benchmark_score", None)
        target_score = getattr(item, "strategic_target_score", None)
        if company_score is None or benchmark_score is None or target_score is None:
            continue
        rows.extend(
            [
                {
                    "维度": item.title,
                    "分数": float(company_score),
                    "系列": "公司得分",
                    "顺序": order,
                },
                {
                    "维度": item.title,
                    "分数": float(benchmark_score),
                    "系列": "市场基准",
                    "顺序": order,
                },
                {
                    "维度": item.title,
                    "分数": float(target_score),
                    "系列": "战略目标要求",
                    "顺序": order,
                },
            ]
        )
    return rows


def render_scorecard_radar(scorecard, *, key: str) -> None:
    """Render company, peer-average benchmark and strategic target polygons."""

    rows = scorecard_comparison_rows(scorecard)
    if len(rows) < 9:
        st.info("至少需要三个已评分维度，才能形成公司—市场基准—战略目标雷达图。")
        return
    styles = {
        "公司得分": {"color": "#356B77", "dash": "solid", "fill": "toself"},
        "市场基准": {"color": "#D58A3A", "dash": "dot", "fill": "none"},
        "战略目标要求": {"color": "#182338", "dash": "dash", "fill": "none"},
    }
    figure = go.Figure()
    for series in ("战略目标要求", "市场基准", "公司得分"):
        values = sorted(
            (row for row in rows if row["系列"] == series),
            key=lambda row: int(row["顺序"]),
        )
        theta = [str(row["维度"]) for row in values]
        radii = [float(row["分数"]) for row in values]
        if not theta:
            continue
        theta.append(theta[0])
        radii.append(radii[0])
        style = styles[series]
        figure.add_trace(
            go.Scatterpolar(
                r=radii,
                theta=theta,
                mode="lines+markers",
                name=series,
                fill=style["fill"],
                fillcolor="rgba(53,107,119,0.14)" if series == "公司得分" else None,
                line={"color": style["color"], "width": 3, "dash": style["dash"]},
                marker={"color": style["color"], "size": 7},
                hovertemplate="%{theta}<br>" + series + "：%{r:.1f}<extra></extra>",
            )
        )
    figure.update_layout(
        height=560,
        margin={"l": 90, "r": 90, "t": 55, "b": 70},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#182338", "size": 13},
        legend={"orientation": "h", "y": -0.12, "x": 0.5, "xanchor": "center"},
        polar={
            "bgcolor": "rgba(0,0,0,0)",
            "radialaxis": {
                "visible": True,
                "range": [0, 100],
                "tickvals": [0, 20, 40, 60, 80, 100],
                "gridcolor": "#DCE4E7",
                "linecolor": "#CAD5D9",
            },
            "angularaxis": {"gridcolor": "#E4EAEC", "linecolor": "#CAD5D9"},
        },
    )
    st.plotly_chart(
        figure,
        use_container_width=True,
        key=key,
        config={"displayModeBar": False, "responsive": True},
    )


def render_bullet_points(items: list[str], *, fallback: str = "未识别") -> None:
    values = [str(item).strip() for item in items if str(item).strip()]
    for item in values or [fallback]:
        st.markdown(f"- {item}")

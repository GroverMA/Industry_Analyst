"""Shared market-benchmark visuals for company strategy workspaces."""

from __future__ import annotations

import streamlit as st


def scorecard_comparison_rows(scorecard) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for order, item in enumerate(scorecard.dimensions):
        company_score = getattr(item, "score", None)
        benchmark_score = getattr(item, "benchmark_score", None)
        if company_score is None or benchmark_score is None:
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
            ]
        )
    return rows


def render_scorecard_radar(scorecard, *, key: str) -> None:
    """Render company and market benchmark on one 0-100 radar scale."""

    rows = scorecard_comparison_rows(scorecard)
    if not rows:
        st.info("当前评分资料不足，暂时无法形成公司—市场基准雷达图。")
        return
    order = [item.title for item in scorecard.dimensions if item.score is not None]
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "height": 430,
        "data": {"values": rows},
        "mark": {
            "type": "line",
            "interpolate": "linear-closed",
            "point": {"filled": True, "size": 70},
            "strokeWidth": 3,
        },
        "encoding": {
            "theta": {
                "field": "维度",
                "type": "nominal",
                "sort": order,
                "axis": {"labelLimit": 160},
            },
            "radius": {
                "field": "分数",
                "type": "quantitative",
                "scale": {"domain": [0, 100]},
                "axis": {"title": None, "tickCount": 5},
            },
            "color": {
                "field": "系列",
                "type": "nominal",
                "scale": {
                    "domain": ["公司得分", "市场基准"],
                    "range": ["#356B77", "#D58A3A"],
                },
                "legend": {"orient": "bottom", "title": None},
            },
            "detail": {"field": "系列"},
            "order": {"field": "顺序", "type": "quantitative"},
            "tooltip": [
                {"field": "维度", "type": "nominal"},
                {"field": "系列", "type": "nominal"},
                {"field": "分数", "type": "quantitative", "format": ".1f"},
            ],
        },
    }
    st.vega_lite_chart(spec=spec, use_container_width=True, key=key)


def render_bullet_points(items: list[str], *, fallback: str = "未识别") -> None:
    values = [str(item).strip() for item in items if str(item).strip()]
    for item in values or [fallback]:
        st.markdown(f"- {item}")

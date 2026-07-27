from __future__ import annotations

import inspect
import io
from datetime import UTC, datetime
from types import SimpleNamespace

from docx import Document
from pypdf import PdfReader

from src.services.report_export import (
    ReportExportContext,
    build_report_docx,
    build_report_pdf,
    project_report_context,
)
from src.ui.theme import apply_theme


SAMPLE_MARKDOWN = """# 中国分子诊断行业研究报告

## 执行摘要

中国分子诊断行业的增长需要同时核验需求、支付与技术商业化条件。

## 行业定义与研究口径

> 核心市场不包含第三方医学检验服务，所有市场规模应使用同一统计口径。

- 产品范围：核酸与分子检测相关仪器、试剂及配套耗材
- 地理范围：中国大陆
- 证据来源：[国家药监局](https://www.nmpa.gov.cn/)

## 市场现状与竞争格局

主要结论必须区分**事实**、分析师推断与预测。

## 未来趋势

- 基准情景：临床需求持续扩展
- 加速情景：创新检测获得支付支持
- 受阻情景：价格和合规压力抑制商业化

| 维度 | 判断 | 证据状态 |
|---|---|---|
| 临床需求 | 稳步扩展 | 已审核 |
| 支付环境 | 仍需监测 | 存在缺口 |
"""


def context() -> ReportExportContext:
    return ReportExportContext(
        title="中国分子诊断行业研究报告",
        markdown=SAMPLE_MARKDOWN,
        industry="分子诊断",
        region="中国",
        time_horizon="2026-2030",
        report_status="经人工审核的通用行业研究报告",
        generated_at=datetime(2026, 7, 27, tzinfo=UTC),
        sop_label="沙利文行业研究 SOP v1.0.0",
    )


def test_word_export_is_editable_and_contains_report_content() -> None:
    payload = build_report_docx(context())

    assert payload.startswith(b"PK")
    document = Document(io.BytesIO(payload))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "中国分子诊断行业研究报告" in text
    assert "沙利文行业研究 SOP v1.0.0" in text
    assert "市场现状与竞争格局" in text
    assert len(document.tables) == 1
    assert document.tables[0].cell(1, 0).text == "临床需求"
    hyperlink_targets = [
        relationship.target_ref
        for relationship in document.part.rels.values()
        if relationship.reltype.endswith("/hyperlink")
    ]
    assert "https://www.nmpa.gov.cn/" in hyperlink_targets


def test_pdf_export_is_paginated_and_has_metadata() -> None:
    payload = build_report_pdf(context())

    assert payload.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(payload))
    assert len(reader.pages) >= 2
    assert reader.metadata.title == "中国分子诊断行业研究报告"


def test_project_context_uses_the_projects_sop_version() -> None:
    project = SimpleNamespace(
        industry="工业机器人",
        region="全球",
        time_horizon="2026-2030",
        research_brief_artifact=SimpleNamespace(
            methodology=SimpleNamespace(
                sop_name="沙利文行业研究 SOP",
                sop_version="1.0.0",
            )
        ),
    )

    export = project_report_context(
        project,
        title="全球工业机器人行业研究",
        markdown="# 报告",
        report_status="经人工审核",
        generated_at=datetime(2026, 7, 27, tzinfo=UTC),
    )

    assert export.sop_label == "沙利文行业研究 SOP v1.0.0"


def test_download_button_theme_forces_white_text() -> None:
    source = inspect.getsource(apply_theme)

    assert ".stDownloadButton > button" in source
    assert "color: #FFFFFF !important" in source

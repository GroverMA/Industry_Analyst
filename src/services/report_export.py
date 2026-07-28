"""Professional Word and PDF exports for human-reviewed research reports."""

from __future__ import annotations

import html
import io
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ACCENT = "356B77"
ACCENT_DARK = "234D57"
INK = "172033"
MUTED = "667085"
LIGHT_FILL = "EEF5F5"
REPORT_FONT = "Calibri"
PDF_CJK_FONT = "IndustryReportCJK"
WORD_CJK_FONT_CANDIDATES = (
    ("Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ("Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
    ("Arial Unicode MS", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ("Hiragino Sans GB", "/System/Library/Fonts/Hiragino Sans GB.ttc"),
)
PDF_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
)


def _resolve_word_cjk_font() -> str:
    for family, location in WORD_CJK_FONT_CANDIDATES:
        if Path(location).is_file():
            return family
    return "Noto Sans CJK SC"


REPORT_CJK_FONT = _resolve_word_cjk_font()


@dataclass(frozen=True)
class ReportExportContext:
    title: str
    markdown: str
    industry: str
    region: str
    time_horizon: str
    report_status: str
    generated_at: datetime
    sop_label: str | None = None


def project_report_context(
    project,
    *,
    title: str,
    markdown: str,
    report_status: str,
    generated_at: datetime,
) -> ReportExportContext:
    """Create one export context for both quick and advanced workspaces."""

    methodology = getattr(project.research_brief_artifact, "methodology", None)
    sop_label = None
    if methodology is not None:
        sop_label = f"{methodology.sop_name} v{methodology.sop_version}"
    return ReportExportContext(
        title=title,
        markdown=markdown,
        industry=project.industry,
        region=project.region,
        time_horizon=project.time_horizon,
        report_status=report_status,
        generated_at=generated_at,
        sop_label=sop_label,
    )


def build_report_docx(context: ReportExportContext) -> bytes:
    """Build a polished, editable Word report using business-report styling."""

    document = Document()
    _configure_document(document, context)
    _add_word_cover(document, context)
    document.add_page_break()
    _add_markdown_to_word(document, context.markdown, skip_first_title=True)

    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def build_report_pdf(context: ReportExportContext) -> bytes:
    """Build a paginated PDF without depending on LibreOffice at runtime."""

    pdf_font = _register_pdf_font()

    stream = io.BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=LETTER,
        rightMargin=0.82 * inch,
        leftMargin=0.82 * inch,
        topMargin=0.76 * inch,
        bottomMargin=0.72 * inch,
        title=context.title,
        author="Industry Analyst OS",
        subject=context.report_status,
    )
    styles = _pdf_styles(pdf_font)
    story = _pdf_cover(context, styles)
    story.append(PageBreak())
    story.extend(_markdown_to_pdf(context.markdown, styles, skip_first_title=True))
    document.build(
        story,
        canvasmaker=lambda *args, **kwargs: _NumberedCanvas(
            *args,
            report_title=context.title,
            **kwargs,
        ),
    )
    return stream.getvalue()


def _register_pdf_font() -> str:
    """Embed a real CJK font so Chinese remains visible across PDF readers."""

    try:
        pdfmetrics.getFont(PDF_CJK_FONT)
        return PDF_CJK_FONT
    except KeyError:
        pass

    configured = os.getenv("INDUSTRY_REPORT_CJK_FONT")
    candidates = ((configured,) if configured else ()) + PDF_FONT_CANDIDATES
    for candidate in candidates:
        font_path = Path(candidate).expanduser()
        if not font_path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(PDF_CJK_FONT, str(font_path), subfontIndex=0))
        except Exception:
            continue
        return PDF_CJK_FONT

    # Streamlit Community Cloud does not guarantee a local CJK font file.
    # ReportLab's standard CID font keeps Chinese PDF generation available
    # without a system package or a private bundled asset.
    fallback_name = "STSong-Light"
    try:
        pdfmetrics.getFont(fallback_name)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(fallback_name))
    return fallback_name


def _configure_document(document: Document, context: ReportExportContext) -> None:
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    section.different_first_page_header_footer = True

    document.core_properties.title = context.title
    document.core_properties.subject = context.report_status
    document.core_properties.author = "Industry Analyst OS"
    document.core_properties.keywords = "industry research, evidence, human review"

    styles = document.styles
    normal = styles["Normal"]
    _set_style_font(normal, REPORT_FONT, REPORT_CJK_FONT, 11, INK)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.10

    heading_tokens = {
        "Heading 1": (16, ACCENT, 16, 8),
        "Heading 2": (13, ACCENT, 12, 6),
        "Heading 3": (12, ACCENT_DARK, 8, 4),
    }
    for style_name, (size, color, before, after) in heading_tokens.items():
        style = styles[style_name]
        _set_style_font(style, REPORT_FONT, REPORT_CJK_FONT, size, color, bold=True)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    bullet = styles["List Bullet"]
    _set_style_font(bullet, REPORT_FONT, REPORT_CJK_FONT, 11, INK)
    bullet.paragraph_format.left_indent = Inches(0.5)
    bullet.paragraph_format.first_line_indent = Inches(-0.25)
    bullet.paragraph_format.space_after = Pt(8)
    bullet.paragraph_format.line_spacing = 1.167

    header = section.header
    header.is_linked_to_previous = False
    header_paragraph = header.paragraphs[0]
    header_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = header_paragraph.add_run("INDUSTRY ANALYST OS  |  HUMAN-REVIEWED RESEARCH")
    _set_run_font(run, REPORT_FONT, REPORT_CJK_FONT, 8.5, MUTED, bold=True)

    footer = section.footer
    footer.is_linked_to_previous = False
    footer_paragraph = footer.paragraphs[0]
    footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    label = footer_paragraph.add_run("Industry Analyst OS  |  ")
    _set_run_font(label, REPORT_FONT, REPORT_CJK_FONT, 8.5, MUTED)
    _add_page_field(footer_paragraph)


def _add_word_cover(document: Document, context: ReportExportContext) -> None:
    for _ in range(4):
        document.add_paragraph()
    kicker = document.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_after = Pt(18)
    run = kicker.add_run("INDUSTRY RESEARCH REPORT")
    _set_run_font(run, REPORT_FONT, REPORT_CJK_FONT, 10, ACCENT, bold=True)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(10)
    title_run = title.add_run(context.title)
    _set_run_font(title_run, REPORT_FONT, REPORT_CJK_FONT, 28, INK, bold=True)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(26)
    subtitle_run = subtitle.add_run(
        f"{context.industry}  |  {context.region}  |  {context.time_horizon}"
    )
    _set_run_font(subtitle_run, REPORT_FONT, REPORT_CJK_FONT, 13, ACCENT_DARK)

    status = document.add_paragraph()
    status.alignment = WD_ALIGN_PARAGRAPH.CENTER
    status.paragraph_format.space_after = Pt(8)
    status_run = status.add_run(context.report_status)
    _set_run_font(status_run, REPORT_FONT, REPORT_CJK_FONT, 10.5, MUTED, bold=True)

    if context.sop_label:
        sop = document.add_paragraph()
        sop.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sop.paragraph_format.space_after = Pt(4)
        sop_run = sop.add_run(f"Methodology: {context.sop_label}")
        _set_run_font(sop_run, REPORT_FONT, REPORT_CJK_FONT, 9.5, MUTED)

    date = document.add_paragraph()
    date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_run = date.add_run(context.generated_at.strftime("%Y-%m-%d"))
    _set_run_font(date_run, REPORT_FONT, REPORT_CJK_FONT, 10, MUTED)


def _add_markdown_to_word(
    document: Document,
    markdown: str,
    *,
    skip_first_title: bool,
) -> None:
    first_heading_skipped = False
    for kind, text, level in _markdown_blocks(markdown):
        if kind == "heading":
            if level == 1 and skip_first_title and not first_heading_skipped:
                first_heading_skipped = True
                continue
            style = (
                "Heading 1"
                if level <= 2
                else "Heading 2"
                if level == 3
                else "Heading 3"
            )
            paragraph = document.add_paragraph(style=style)
            _add_word_inline(paragraph, text)
        elif kind == "bullet":
            paragraph = document.add_paragraph(style="List Bullet")
            if level > 0:
                paragraph.paragraph_format.left_indent = Inches(0.75)
            _add_word_inline(paragraph, text)
        elif kind == "quote":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.18)
            paragraph.paragraph_format.right_indent = Inches(0.12)
            paragraph.paragraph_format.space_before = Pt(3)
            paragraph.paragraph_format.space_after = Pt(5)
            _shade_paragraph(paragraph, LIGHT_FILL)
            _add_left_border(paragraph, ACCENT)
            _add_word_inline(paragraph, text)
        elif kind == "table":
            _add_word_table(document, text)
        else:
            paragraph = document.add_paragraph()
            _add_word_inline(paragraph, text)


def _markdown_blocks(markdown: str):
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if not line.strip():
            index += 1
            continue
        if (
            line.lstrip().startswith("|")
            and index + 1 < len(lines)
            and _is_markdown_table_separator(lines[index + 1])
        ):
            rows = [_table_cells(line)]
            index += 2
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append(_table_cells(lines[index]))
                index += 1
            width = max(len(row) for row in rows)
            yield "table", [row + [""] * (width - len(row)) for row in rows], 0
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            yield "heading", heading.group(2).strip(), len(heading.group(1))
            index += 1
            continue
        quote = re.match(r"^>\s?(.*)$", line)
        if quote:
            yield "quote", quote.group(1).strip(), 0
            index += 1
            continue
        bullet = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if bullet:
            yield "bullet", bullet.group(2).strip(), 1 if len(bullet.group(1)) >= 2 else 0
            index += 1
            continue
        yield "paragraph", line.strip(), 0
        index += 1


def _is_markdown_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _add_word_table(document: Document, rows: list[list[str]]) -> None:
    table = document.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    table.autofit = True
    for row_index, values in enumerate(rows):
        for column_index, value in enumerate(values):
            cell = table.cell(row_index, column_index)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(2)
            _add_word_inline(paragraph, value)
            if row_index == 0:
                _shade_cell(cell, ACCENT)
            for run in paragraph.runs:
                _set_run_font(
                    run,
                    REPORT_FONT,
                    REPORT_CJK_FONT,
                    8.5 if row_index == 0 else 8.2,
                    "FFFFFF" if row_index == 0 else INK,
                    bold=row_index == 0,
                )
    document.add_paragraph().paragraph_format.space_after = Pt(2)


def _shade_cell(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


INLINE_PATTERN = re.compile(r"(\*\*.+?\*\*|`.+?`|\[[^\]]+\]\([^)]+\))")


def _add_word_inline(paragraph, text: str) -> None:
    cursor = 0
    for match in INLINE_PATTERN.finditer(text):
        if match.start() > cursor:
            run = paragraph.add_run(text[cursor:match.start()])
            _set_run_font(run, REPORT_FONT, REPORT_CJK_FONT, 11, INK)
        token = match.group(0)
        if token.startswith("**"):
            run = paragraph.add_run(token[2:-2])
            _set_run_font(run, REPORT_FONT, REPORT_CJK_FONT, 11, INK, bold=True)
        elif token.startswith("`"):
            run = paragraph.add_run(token[1:-1])
            _set_run_font(run, "Courier New", REPORT_CJK_FONT, 9.5, ACCENT_DARK)
        else:
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()
            _add_hyperlink(paragraph, label, url)
        cursor = match.end()
    if cursor < len(text):
        run = paragraph.add_run(text[cursor:])
        _set_run_font(run, REPORT_FONT, REPORT_CJK_FONT, 11, INK)


def _add_hyperlink(paragraph, label: str, url: str) -> None:
    relationship_id = paragraph.part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), ACCENT)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.extend([color, underline])
    text = OxmlElement("w:t")
    text.text = label
    run.extend([properties, text])
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _set_style_font(style, latin: str, east_asia: str, size: float, color: str, bold=False):
    style.font.name = latin
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor.from_string(color)
    style.font.bold = bold
    style._element.rPr.rFonts.set(qn("w:ascii"), latin)
    style._element.rPr.rFonts.set(qn("w:hAnsi"), latin)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), east_asia)


def _set_run_font(run, latin: str, east_asia: str, size: float, color: str, bold=False):
    run.font.name = latin
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    run.font.bold = bold
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), latin)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), latin)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), east_asia)


def _add_page_field(paragraph) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instruction, separate, text, end])


def _shade_paragraph(paragraph, fill: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _add_left_border(paragraph, color: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    borders = properties.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        properties.append(borders)
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:space"), "8")
    left.set(qn("w:color"), color)
    borders.append(left)


def _pdf_styles(font_name: str):
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9.5,
            leading=14.2,
            textColor=colors.HexColor(f"#{INK}"),
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "h1": ParagraphStyle(
            "ReportH1",
            fontName=font_name,
            fontSize=15,
            leading=20,
            textColor=colors.HexColor(f"#{ACCENT}"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
            wordWrap="CJK",
        ),
        "h2": ParagraphStyle(
            "ReportH2",
            fontName=font_name,
            fontSize=12.5,
            leading=17,
            textColor=colors.HexColor(f"#{ACCENT_DARK}"),
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
            wordWrap="CJK",
        ),
        "bullet": ParagraphStyle(
            "ReportBullet",
            fontName=font_name,
            fontSize=9.5,
            leading=14.2,
            leftIndent=18,
            firstLineIndent=-10,
            textColor=colors.HexColor(f"#{INK}"),
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "quote": ParagraphStyle(
            "ReportQuote",
            fontName=font_name,
            fontSize=9.3,
            leading=13.8,
            textColor=colors.HexColor(f"#{ACCENT_DARK}"),
            wordWrap="CJK",
        ),
        "cover_kicker": ParagraphStyle(
            "CoverKicker",
            fontName=font_name,
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor(f"#{ACCENT}"),
            spaceAfter=18,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle",
            fontName=font_name,
            fontSize=25,
            leading=32,
            alignment=TA_CENTER,
            textColor=colors.HexColor(f"#{INK}"),
            spaceAfter=12,
            wordWrap="CJK",
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            fontName=font_name,
            fontSize=12,
            leading=17,
            alignment=TA_CENTER,
            textColor=colors.HexColor(f"#{ACCENT_DARK}"),
            spaceAfter=24,
            wordWrap="CJK",
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta",
            fontName=font_name,
            fontSize=9.5,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor(f"#{MUTED}"),
            spaceAfter=5,
            wordWrap="CJK",
        ),
    }


def _pdf_cover(context: ReportExportContext, styles) -> list:
    story = [Spacer(1, 1.45 * inch)]
    story.append(Paragraph("INDUSTRY RESEARCH REPORT", styles["cover_kicker"]))
    story.append(Paragraph(_pdf_inline(context.title), styles["cover_title"]))
    story.append(
        Paragraph(
            _pdf_inline(f"{context.industry}  |  {context.region}  |  {context.time_horizon}"),
            styles["cover_subtitle"],
        )
    )
    story.append(Paragraph(_pdf_inline(context.report_status), styles["cover_meta"]))
    if context.sop_label:
        story.append(
            Paragraph(_pdf_inline(f"Methodology: {context.sop_label}"), styles["cover_meta"])
        )
    story.append(
        Paragraph(context.generated_at.strftime("%Y-%m-%d"), styles["cover_meta"])
    )
    return story


def _markdown_to_pdf(markdown: str, styles, *, skip_first_title: bool) -> list:
    story = []
    first_heading_skipped = False
    for kind, text, level in _markdown_blocks(markdown):
        if kind == "heading":
            if level == 1 and skip_first_title and not first_heading_skipped:
                first_heading_skipped = True
                continue
            story.append(Paragraph(_pdf_inline(text), styles["h1" if level <= 2 else "h2"]))
        elif kind == "bullet":
            prefix = "- " if level == 0 else "  - "
            story.append(Paragraph(_pdf_inline(prefix + text), styles["bullet"]))
        elif kind == "quote":
            table = Table(
                [[Paragraph(_pdf_inline(text), styles["quote"]) ]],
                colWidths=[6.72 * inch],
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(f"#{LIGHT_FILL}")),
                        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor(f"#{ACCENT}")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.extend([table, Spacer(1, 5)])
        elif kind == "table":
            story.extend([_pdf_table(text, styles), Spacer(1, 7)])
        else:
            story.append(Paragraph(_pdf_inline(text), styles["body"]))
    return story


def _pdf_table(rows: list[list[str]], styles) -> Table:
    column_count = len(rows[0])
    data = []
    for row_index, row in enumerate(rows):
        rendered_row = []
        for cell in row:
            content = _pdf_inline(cell)
            if row_index == 0:
                content = f"<font color='#FFFFFF'><b>{content}</b></font>"
            rendered_row.append(Paragraph(content, styles["body"]))
        data.append(rendered_row)
    table = Table(
        data,
        colWidths=[6.72 * inch / column_count] * column_count,
        repeatRows=1,
    )
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{ACCENT}")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D4D8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for row_index in range(2, len(rows), 2):
        commands.append(
            ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F7FAFA"))
        )
    table.setStyle(TableStyle(commands))
    return table


def _pdf_inline(text: str) -> str:
    pieces: list[str] = []
    cursor = 0
    for match in INLINE_PATTERN.finditer(text):
        pieces.append(html.escape(text[cursor:match.start()]))
        token = match.group(0)
        if token.startswith("**"):
            pieces.append(f"<b>{html.escape(token[2:-2])}</b>")
        elif token.startswith("`"):
            pieces.append(f"<font color='#{ACCENT_DARK}'>{html.escape(token[1:-1])}</font>")
        else:
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()
            pieces.append(
                f"<link href='{html.escape(url, quote=True)}' color='#{ACCENT}'>"
                f"{html.escape(label)}</link>"
            )
        cursor = match.end()
    pieces.append(html.escape(text[cursor:]))
    return "".join(pieces)


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, report_title: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.report_title = report_title
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(page_count)
            super().showPage()
        super().save()

    def _draw_page_number(self, page_count: int):
        page_number = self._pageNumber
        if page_number == 1:
            return
        self.saveState()
        self.setStrokeColor(colors.HexColor("#D7E0E2"))
        self.setLineWidth(0.4)
        self.line(0.82 * inch, 0.56 * inch, 7.68 * inch, 0.56 * inch)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor(f"#{MUTED}"))
        self.drawString(0.82 * inch, 0.38 * inch, "Industry Analyst OS")
        self.drawRightString(7.68 * inch, 0.38 * inch, f"{page_number} / {page_count}")
        self.restoreState()

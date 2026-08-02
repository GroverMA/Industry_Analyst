# Trident Research Paths and Report Export Design QA

- Source visual truth: `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-6b4e4d95-da40-4720-b8c9-6167008c1626.png`
- Browser-rendered implementation: `/private/tmp/trident-research-paths.png`
- Implementation URL: `http://127.0.0.1:8502/`
- Viewport: 1600 x 1000 CSS px.
- State: first-entry research-path selection, followed by the build-first project home.

## Full-view comparison evidence

The source showed two identity cards with role and permission language. The implementation keeps the balanced two-card composition while reframing the choice as two research paths. Both cards have equal size, border, typography, content density, and button weight. The page now uses the required `CHOOSE YOUR RESEARCH PATH` eyebrow, title, subtitle, path descriptions, five-step summaries, and persistence statement.

The project home was checked after entering build-first research. The hero displays the `Trident` brand, the slogan `Dive Deep into Industries. Surface with Direction.`, and the English descriptor `ENTERPRISE INDUSTRY RESEARCH & STRATEGIC DECISION INTELLIGENCE`. The sidebar exposes a persistent research-path switch without presenting the paths as user roles.

## Report display and export evidence

- The report display panel controls font family, title and body colors, report title, level-one and level-two heading sizes, body size, and line height.
- The same immutable style object is passed to the web preview, Word builder, and PDF builder for build-first and review-first flows, including general and enterprise reports.
- A deliberately customized report was exported to Word and PDF. The PDF was rendered to page images and visually checked for title hierarchy, color, body size, and line spacing.
- Word content, paragraph hierarchy, font sizes, colors, and line spacing were inspected programmatically after export. The text and styling are present in the generated DOCX package.
- A deliberately malformed sample containing sentence-closing punctuation at the beginning of paragraphs, headings, bullets, quotes, and table cells was exported. Shared normalization removed those leading marks before web rendering and both document exports.

## Interaction and runtime checks

- Entered the build-first path through `从问题开始` and confirmed the existing project home rendered without a Streamlit error component.
- Confirmed the sidebar presents `当前研究方式 · 构建式研究` and retains the in-project switch entry.
- Confirmed project data is not recreated by a path switch; both views operate on the same project object, evidence collection, report artifact, and revision state.
- Confirmed the report settings panel is used by every Word/PDF download call site in both research paths.
- Automated application, workflow, report-generation, Word-export, and PDF-export tests passed.

## Findings

- No P0, P1, or P2 issue remains in the tested path-selection, project-home, web-preview, Word-export, or PDF-export states.
- The prohibited identity wording is absent from user-facing application code.
- The two research paths retain equal visual priority and make their opposite research order explicit.
- Typography controls now affect downloadable deliverables instead of changing only the browser preview.
- Paragraph-start punctuation is normalized at the final rendering boundary, protecting all three formats from upstream model variation.

final result: passed

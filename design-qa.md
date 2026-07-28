# Design QA — Home, Pipeline and Evidence Review

## Source visual truth

- Home advantage cards to be relocated and compressed: `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-7de90d73-583c-428b-b02d-283273f208fd.png` (2280 × 490 px).
- Home hero copy reference: `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-666b0e0a-a4cd-47e8-92a4-315b14dbd56a.png`.
- Pipeline density reference: `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-a15e6b3e-0e1c-46b6-8f00-f4be75a7f66a.png`.
- Evidence review references: `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-66149a91-e98f-4a59-b75a-3ed449c22b4a.png` and `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-c3d5e453-e74b-4b26-a1b6-c335dd06225c.png`.

## Browser-rendered implementation evidence

- Desktop home: `/Users/calin/Documents/PhD Application 2/industry-analyst-os/visuals/home-redesign-desktop-1440.png`.
- Mobile home final: `/Users/calin/Documents/PhD Application 2/industry-analyst-os/visuals/home-redesign-mobile-390-final.png`.
- Desktop viewport: 1440 × 1000 CSS px; implementation capture 1440 × 1000 px; browser density normalized by the in-app browser capture.
- Mobile viewport: 390 × 844 CSS px; implementation capture 390 × 844 px.
- State: no active project for home; China molecular diagnostics case loaded for the pipeline inspection.

## Full-view and focused comparison evidence

- Home: the former three full-width advantage cards were removed from the bottom and condensed into the right-side `仅供浏览` panel beside the case card. The left side is explicitly marked `需要填写` and contains only research inputs.
- Copy: the hero now exactly reads `你的专属AI行业分析师：洞察未来趋势与竞争格局，发现市场机会，找到增长路径。`
- Pipeline: browser inspection found 11 steps in one horizontal track. The track measured 975.2 × 62.7 CSS px, and every step shared the same row with only a four-pixel text-wrap offset. Names are above numbered nodes and the completed portion has a teal line fill.
- Evidence review: the table no longer exposes A/B/C/D grades. It presents `质量评分`, `问题相关度`, `对应研究问题` and source links. The explanation discloses all five scoring components and both recommendation thresholds.
- Mobile: at 390 px the sidebar starts collapsed, the page has no horizontal overflow, the hero is readable, and the input region appears before the browsing-only case/advantage region.
- Focused image comparison was needed only for the home hierarchy; pipeline and evidence changes are interaction/data states rather than a request to clone the old screenshots, so browser DOM measurement and component assertions were used for those focused checks.

## Required fidelity surfaces

- Fonts and typography: retained the existing sans-serif family, dark navy hierarchy and compact teal eyebrow; no decorative symbols or emoji were introduced.
- Spacing and layout rhythm: hero padding reduced; left/right areas remain visually distinct; advantage information is compressed without reducing label legibility; pipeline height is approximately 63 px rather than two rows of large cards.
- Colors and tokens: retained the white, slate and teal token system. Primary buttons and completed progress nodes use the existing accent with white foreground.
- Image quality and assets: the requested screens contain no product imagery or custom illustration assets; no placeholder, generated, SVG or CSS-drawn image asset was introduced.
- Copy and content: required hero sentence, `需要填写`, `仅供浏览`, quality scoring language and automatic coverage-repair language are present.

## Interaction and runtime checks

- Home form inputs, strategy toggle, case loading, workspace-mode switch and new-project navigation remain interactive.
- Loading the case renders all numbered pipeline nodes in one horizontal track.
- Mobile sidebar auto-collapses and can be reopened.
- Browser console errors checked: none.
- Automated regression suite: all tests pass.

## Comparison history

| Iteration | Finding | Severity | Fix | Post-fix evidence |
|---|---|---:|---|---|
| 1 | Product advantages competed with the user input form and consumed a full row. | P1 | Moved and compressed them into the right browsing-only panel. | Desktop DOM and home capture show one input column plus one browsing panel. |
| 1 | Pipeline used two rows of large step cards. | P1 | Replaced with one compact numbered horizontal progress track. | Browser measured one track with 11 nodes and approximately 63 px height. |
| 1 | Evidence grade letters and QA label were unexplained and recommendation could omit questions. | P1 | Removed letters, disclosed the score formula, added relevance and question mapping, and implemented minimum-set coverage. | UI assertions and service tests pass. |
| 1 | Mobile opened with the 300 px sidebar over the form. | P1 | Changed the initial sidebar policy to responsive `auto`. | Final 390 × 844 capture shows the collapsed sidebar and readable form. |
| 2 | A completed task could still omit one of its questions. | P0 | Added Prompt/task question ledgers, Gate 1 coverage validation and one-click per-gap supplemental retrieval. | Regression test rejects an accepted evidence set that omits T01-Q2. |
| 2 | One malformed large model response invalidated all five analysis modules. | P0 | Generate and repair each module independently; failed modules become explicit evidence gaps. | Structured-analysis failure tests pass without losing valid modules. |

## Findings

- No actionable P0, P1 or P2 visual or interaction differences remain in the requested scope.
- P3 follow-up: the English internal pipeline labels can be localized later if a fully Chinese interface is desired.

## Final result

final result: passed

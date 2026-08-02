# Design QA — Dual-role report workflow

## Visual sources

- Earlier home, pipeline and evidence references:
  - `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-7de90d73-583c-428b-b02d-283273f208fd.png`
  - `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-666b0e0a-a4cd-47e8-92a4-315b14dbd56a.png`
  - `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-a15e6b3e-0e1c-46b6-8f00-f4be75a7f66a.png`
  - `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-66149a91-e98f-4a59-b75a-3ed449c22b4a.png`
  - `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-c3d5e453-e74b-4b26-a1b6-c335dd06225c.png`
- User workflow reference: `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-2bde83e7-22be-494d-98f6-354f0ade26c8.png`
- Reviewer revision and report-writing references:
  - `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-2665a372-142a-4980-b374-e3239ebca352.png`
  - `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-e3edf0cd-c416-4588-a12d-bf7cb09c46b8.png`
  - `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-7f6d5155-9459-4591-adf4-a65771f3c1cc.png`
  - `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-0483baa0-7beb-40b9-ab29-5a32e247fe66.png`
- Role-entry implementation capture: `visuals/role-selection-final.png`
- Reviewer implementation capture: `visuals/reviewer-workflow-final.png`
- Content Revision progress capture: `visuals/reviewer-content-revision-final.png`
- Side-by-side workflow comparison: `visuals/reviewer-workflow-comparison.png`

## States inspected

- First browser entry before a role is chosen.
- Reviewer identity selected while the existing home and project-creation UI remains available.
- Existing enterprise project opened in Reviewer mode.
- Enterprise inputs missing, with an explicit CTA and report-first workflow visible.
- A real general-industry Reviewer project was run through live web research, five-module industry analysis, Future Intelligence and report export.
- The completed report, Content Revision editor, trace-target selector, Word download and PDF download were inspected in the browser.

## Acceptance checks

- PASS — Earlier verified home hierarchy keeps inputs left and product/case content right.
- PASS — Earlier verified Consultant progress and evidence-review interactions remain covered by the regression suite.
- PASS — Responsive sidebar behavior and the existing teal/white design system remain unchanged.
- PASS — The entry screen clearly distinguishes Consultant (author) from Reviewer (reviewer).
- PASS — Role switching is visible in the upper-left sidebar and does not replace the home experience.
- PASS — The Reviewer progress line removes Web Research, Gate 1 and Gate 2 as operating steps.
- PASS — Enterprise Report appears immediately after Gate 0, followed by retrospective workpapers.
- PASS — General and enterprise Reviewer flows place Content Revision immediately after the report.
- PASS — The revision surface supports direct report editing, AI-assisted questions across Reference Check, Industry Analysis, Future Intelligence, Company Scorecard and Action Plan, repeated version acceptance, and finalization.
- PASS — Accepted revision rounds retain explicit research-logic amendments for the selected trace layer instead of silently overwriting the source workpaper.
- PASS — Internal evidence warnings remain in the Reviewer workbench and are not rendered as client-facing report paragraphs.
- PASS — The real model-backed general workflow completed after a hosted forecasting timeout was recovered into an evidence-linked three-scenario forecast.
- PASS — Word and PDF review-report downloads both rendered after the live workflow completed.
- PASS — The implementation retains the established white, transparent, teal and restrained-border visual system.
- PASS — Primary buttons use white text on teal and remain readable.
- PASS — No broken layout, cropped primary CTA, inaccessible navigation, or blocking visual defect was found at the tested desktop viewport.
- PASS — Browser console inspection found no runtime errors in the verified Reviewer workspace state.

## Final result

PASSED — no unresolved P0, P1 or P2 visual issues.

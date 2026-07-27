# Design QA — Project History Sidebar

## Scope

- Screen: project home with the browser-local history sidebar open.
- State: no active project; one saved in-progress China molecular diagnostics project at 10%, Research Planning; no completed project; folder manager collapsed.
- Reference: `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-a20fd585-1023-40db-a02b-d2d3e105eb54.png`.
- Implementation: `/private/tmp/industry-analyst-os-design-qa/implementation-desktop-final.png`.
- Side-by-side comparison: `/private/tmp/industry-analyst-os-design-qa/sidebar-comparison-final.png`.

## Viewports and normalization

- Desktop implementation viewport: 1280 × 720 CSS pixels, device pixel ratio 1.
- Mobile implementation viewport: 390 × 844 CSS pixels, device pixel ratio 1.
- Reference source dimensions: 586 × 1204 pixels.
- Focused sidebar comparison normalized both captures to 844 pixels in height; the implementation was cropped to the 300-pixel sidebar before normalization.

## Full-view checks

- The sidebar, home hero, new-project form, and case panel remain readable at 1280 × 720.
- At 390 × 844, the sidebar opens as an opaque white drawer and closes without horizontal overflow.
- The main call to action, search, project status groups, progress text, and folder manager remain reachable on both viewports.

## Comparison history

| Iteration | Finding | Severity | Change | Result |
|---|---|---:|---|---|
| 1 | The mobile sidebar inherited transparency, allowing the underlying page to show through. | P1 | Forced an opaque white mobile sidebar background and retained the existing border hierarchy. | Fixed |
| 1 | The old navigation exposed page names but did not surface project history, resumable progress, or categorization. | P1 | Replaced it with new research, search, in-progress/completed sections, progress/node labels, and folder management. | Fixed |
| 2 | Folder counts were visible, but projects inside a folder were not directly listed in the expanded manager. | P2 | Added project buttons under each folder while preserving the compact collapsed state. | Fixed |

## Interaction checks

- `新建研究` clears the active workspace and returns to the project home without deleting saved history.
- A hard page refresh retains the saved project in IndexedDB.
- Selecting a saved project restores the full `ProjectState`, active page, progress, and current workflow node.
- Folder creation and project movement both update the catalog and survive refresh.
- Project search filters saved project names in the sidebar.

## Final assessment

- P0 issues remaining: none.
- P1 issues remaining: none.
- P2 issues remaining: none in the requested scope.
- Visual system: retained the product's white, slate, and teal visual language; no new image assets were introduced.
- Status: passed for handoff.

# Design QA — Research Project Form Redesign

- Source visual truth: `/var/folders/dp/dwbdn3jx1j36lscl0cpz0g5w0000gn/T/codex-clipboard-385faa94-0b52-4ee9-944f-1c7ec1c7182b.png`
- Source pixels: 1450 × 1498
- Desktop implementation: `visuals/research-form-redesign-final.png`
- Desktop implementation pixels: 1450 × 1159 viewport capture
- Mobile implementation: `visuals/research-form-redesign-mobile-prompt.png`
- Mobile implementation pixels/CSS viewport: 390 × 844 at device scale 1
- State: empty universal-research project form; sidebar collapsed
- Density normalization: source and desktop implementation captured at 1× pixel density; mobile checked separately at its native CSS viewport

## Full-view comparison evidence

The source and final implementation were opened together in the same comparison
pass. The implementation preserves the white professional workspace, dark navy
hierarchy, light borders, modest radii, and teal accent. The existing desktop
case-demonstration column is intentionally retained; the user requested a form
hierarchy and contrast revision, not removal of the demonstration area.

The central change is visible above the long-form input: a pale teal prompt guide
with a solid accent edge identifies the mandatory primary prompt before the user
reaches optional company or decision context. The optional decision field is
visibly labelled and placed after the required research objective.

## Focused-region comparison evidence

Focused inspection covered the primary prompt block, core research textarea,
optional decision field, and primary submit button. This was necessary because
the user's requested changes depend on copy hierarchy and control-state contrast,
which are too small to judge only from a full-page capture.

## Required fidelity surfaces

- **Fonts and typography:** Existing sans-serif stack, weights, line height, and
  dark-navy hierarchy remain consistent. The prompt kicker uses a small uppercase
  weight while the prompt title remains readable and does not compete with the
  screen heading.
- **Spacing and layout rhythm:** The new guide follows the existing form grid,
  aligns with input edges, and preserves vertical rhythm. Desktop keeps the
  existing case-demonstration column; mobile stacks the form without horizontal
  overflow.
- **Colors and visual tokens:** Teal remains the sole accent. The prompt guide
  uses a light solid teal surface and dark text. The primary button uses
  `rgb(53, 107, 119)` with white text; no low-contrast muted paragraph color is
  inherited.
- **Image quality and asset fidelity:** This form contains no imagery, logos,
  illustrations, or non-standard icon assets requiring recreation.
- **Copy and content:** `核心研究目标（必填）` is identified as the main Agent
  prompt. `需要支持的业务决策（可选）` explicitly explains that industry
  landscape research may leave it blank.

## Comparison history

### Iteration 1

- **[P1] Primary button text inherited the global muted paragraph color.**
  Evidence: the teal submit button visually rendered grey text despite a white
  color on the outer button.
  Fix: extended the primary-button rule to Streamlit's `primaryFormSubmit` kind
  and all nested text elements using a starts-with selector and `!important`.
- **[P1] Research objective did not read as the primary prompt.**
  Evidence: the source placed business decision before a similarly styled
  research-objective textarea.
  Fix: moved the mandatory research objective earlier, added an instructional
  prompt guide, increased its input height, and moved optional context below it.
- **[P1] Business decision behaved as a required field.**
  Fix: changed the project schema and both creation/edit forms to accept a blank
  decision while keeping research objective mandatory.

### Iteration 2

Post-fix evidence: `visuals/research-form-redesign-final.png` and
`visuals/research-form-redesign-mobile-prompt.png`.

No actionable P0/P1/P2 findings remain. The form can create an exploratory
industry project with the decision field empty, the button text is visibly white,
the mobile layout has no horizontal overflow, and the browser console is clean.

## Open questions

None for this scoped revision. The two-column desktop composition is an
intentional preservation of the existing product layout rather than a fidelity
error against the cropped source image.

## Implementation checklist

- [x] White primary-button text at every nested Streamlit text layer
- [x] Mandatory research objective presented as the primary prompt
- [x] Optional business decision in schema, UI, and model prompt
- [x] Exploratory project creation tested without a decision
- [x] Desktop and 390 px mobile layout checked
- [x] Console and automated tests checked

## Follow-up polish

No blocking polish remains for this form revision.

final result: passed

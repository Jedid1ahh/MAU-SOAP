# MAU-SOAP system redesign

## Scope

Replacement visual identity and responsive component system for the public site, authentication, Admin, Lecturer, Student, examination, grading, supervision, and result surfaces. Visitor modes: Persuade on the public landing page; Operate everywhere else.

## Confirmed brief

- Treat Admin, Lecturer, and Student experiences with balanced importance.
- Preserve Flask routes, backend logic, form behavior, authorization, and JavaScript hooks.
- Improve frontend wording without changing its meaning.
- Use the supplied Edulearn and Kingster references as a quality bar for education-specific hierarchy, institutional presence, and real photography.
- Remove the generic gradient-card SaaS character and the layout imbalance shown in the supplied screenshots.

## Direction contract

**THESIS:** MAU-SOAP becomes an academic wayfinding system: every screen makes role, course, state, and next action unmistakable. It refuses the category default of pale gradients, oversized rounded cards, and decorative dashboard statistics detached from real tasks.

**OWN-WORLD:** Deep university navy, paper white, slate, and a controlled MAU gold form large page fields. Archivo provides a crisp institutional voice. Components use square-cut panels, fine rules, course-code labels, strong section bands, and restrained shadows. Photography appears only where it establishes real academic context.

**STORY:** The public surface establishes Modibbo Adama University and the secure assessment purpose, then directs each role to one shared sign-in. Inside the portal, users read their role and current course first, scan live states second, and take the next action without searching through ornamental content.

**FIRST VIEWPORT:** A slim navy university utility bar sits above a white masthead. The landing page opens with an edge-to-edge two-column editorial hero: decisive copy and role entry on the left, one documentary university-study photograph on the right, joined by a gold course-status rail. Authentication uses the same photograph as a narrow contextual panel beside a compact form—never a centered floating island.

**FORM:** Academic Wayfinding, selected manually from the user-pinned university-template references because the optional Impeccable concept engine is unavailable in this Personal installation. Manual seed: `manual-academic-wayfinding-2026-09-22`. The system combines campus wayfinding, examination cover sheets, timetable grids, and formal university publications.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Approved visual references

- Public and authentication composition: `.impeccable/mocks/option-c-campus-wayfinding.png` (approved through the user's instruction to produce visual mockups and continue directly into code).
- Dashboard density reference: `.impeccable/mocks/option-b-academic-ledger.png` (supporting composition only; it does not establish a separate identity).
- Do not reproduce generated logos or generated photography. Use the text-first MAU-SOAP identity and separately sourced, licensed photography in shipping templates.

## Memorable moment

Course codes behave like wayfinding markers throughout the portal: a compact gold-accented identifier anchors cards, headings, examination states, and result metadata so users always know which academic space they are in.

## Unresolved decisions

- Replace the text-first MAU identity with the official university logo only when an approved local logo asset is supplied.

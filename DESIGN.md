---
name: MAU-SOAP
description: An academic wayfinding system for secure university assessment.
colors:
  university-navy: "#08264a"
  deep-navy: "#041a33"
  mau-gold: "#f3b61f"
  gold-ink: "#785300"
  paper: "#ffffff"
  campus-mist: "#edf1f4"
  soft-surface: "#f5f7f9"
  ink: "#142234"
  muted-ink: "#526174"
  rule: "#cfd8e2"
  success: "#126b50"
  danger: "#a32638"
typography:
  display:
    fontFamily: "Archivo, Arial, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(3.4rem, 6.2vw, 6.8rem)"
    fontWeight: 800
    lineHeight: 0.9
    letterSpacing: "-0.06em"
  headline:
    fontFamily: "Archivo, Arial, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(2rem, 4vw, 3.5rem)"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Archivo, Arial, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.62
  label:
    fontFamily: "Archivo, Arial, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.7rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0.075em"
rounded:
  sm: "3px"
  md: "6px"
  lg: "8px"
spacing:
  xs: "8px"
  sm: "16px"
  md: "24px"
  lg: "32px"
  xl: "64px"
components:
  button-primary:
    backgroundColor: "{colors.university-navy}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "12px 18px"
    height: "46px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.university-navy}"
    rounded: "{rounded.sm}"
    padding: "12px 18px"
    height: "46px"
  course-marker:
    backgroundColor: "{colors.mau-gold}"
    textColor: "{colors.deep-navy}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "6px 9px"
---

# Design System: MAU-SOAP

## Overview

**Creative North Star: "Academic Wayfinding"**

MAU-SOAP should feel like a well-run university building translated into a digital service: authoritative entry points, visible course labels, clear destinations, and an orderly record of what happens next. Its institutional character comes from navy fields, MAU gold markers, disciplined rules, and documentary campus photography—not ornamental dashboard effects.

The system balances public confidence with operational density. Public and authentication pages may use strong photographic composition; dashboards should prioritize course context and scan speed. The visual language stays calm during high-stakes examination work.

**Key Characteristics:**

- Full-width institutional page bands rather than centered floating app shells.
- Course codes and status labels act as practical wayfinding markers.
- Flat white work surfaces separated by rules, with shadows reserved for exceptional elevation.
- Real education photography on public and sign-in surfaces only.
- Responsive layouts preserve reading order before preserving columns.

## Colors

The palette is institutional and high-contrast: navy establishes authority, gold marks direction and priority, and cool paper neutrals carry dense academic information.

### Primary

- **University Navy:** The dominant masthead, page-heading, primary-action, and timer color.
- **Deep Navy:** A grounding tone for utility bars, footers, and the darkest text fields.

### Secondary

- **MAU Gold:** A deliberately scarce wayfinding accent for course markers, top rules, and primary calls to action on navy.
- **Gold Ink:** Accessible accent text when gold appears on light surfaces.

### Neutral

- **Paper:** The working surface for forms, records, cards, and navigation.
- **Campus Mist:** The page field that separates white work surfaces without visual noise.
- **Ink and Muted Ink:** Primary and supporting text roles.
- **Rule:** The structural divider used in tables, metadata, cards, and summaries.

**The Gold Means Direction Rule.** Gold identifies a destination, course, or decisive action; it is not ambient decoration.

## Typography

**Display Font:** Archivo (with Arial and system sans-serif fallbacks)
**Body Font:** Archivo (with Arial and system sans-serif fallbacks)
**Label Font:** Archivo (with Arial and system sans-serif fallbacks)

**Character:** Archivo gives the portal an administrative, contemporary voice without looking like a generic software dashboard. Weight and scale create hierarchy; decorative type effects do not.

### Hierarchy

- **Display** (800, responsive 3.4–6.8rem, 0.9): Reserved for the public landing statement.
- **Headline** (700, responsive 2–3.5rem, 1.02): Page destinations, dashboards, receipts, and auth titles.
- **Title** (700, 1.3–1.75rem): Course, examination, and section titles.
- **Body** (400, 1rem, 1.62): Instructions and academic records; prose should remain comfortably narrow.
- **Label** (800, 0.7rem, 0.075em, uppercase): Course codes, status, metadata terms, and compact navigation signals.

**The Destination First Rule.** Every screen leads with the destination or task itself; never place a generic eyebrow above the heading.

## Layout

The main application canvas is capped at 90rem with 2rem desktop gutters. Dashboards use a full-width navy heading band followed by ledger-like summary strips and responsive course grids. Public pages may extend edge-to-edge. Authentication uses an approximately 44/56 split between context and form, then collapses to a single column below 56rem.

Spacing follows an 8px base with 16px, 24px, 32px, and 64px structural steps. At narrow widths, journeys and summary strips reduce columns before stacking. Content order, actions, and status remain visible without horizontal scrolling.

## Elevation & Depth

The system is flat by default. Borders, background contrast, strong page bands, and photography create depth. A low ambient shadow is allowed for authentication framing and hover feedback, but routine cards never float.

### Shadow Vocabulary

- **Low ambient** (`0 8px 24px rgb(4 26 51 / 7%)`): Authentication frame only.
- **Responsive hover** (`0 5px 16px rgb(4 26 51 / 6%)`): A subtle acknowledgement on actionable cards.

**The Flat Record Rule.** Academic records and course resources rest on the page; they do not compete through elevation.

## Shapes

Controls and compact cards use square-to-gently softened corners from 3px to 8px. Major layout bands remain square. Course markers are small rectangular tabs, not pills. One-pixel cool-gray rules provide most grouping; gold top rules identify special destinations such as forms and receipts.

## Components

### Buttons

- **Shape:** Compact rectangular control with a 3px radius and 46px minimum height.
- **Primary:** University navy with white text; on navy hero or heading fields, MAU gold with deep-navy text.
- **Hover / Focus:** Hover deepens the fill without lifting. Keyboard focus uses a visible three-pixel gold ring.
- **Secondary:** White with a firm gray border and navy text; on navy bands it becomes a transparent white-outlined control.

### Chips

- **Style:** Small uppercase rectangular labels with restrained padding.
- **State:** Gold marks courses and directional context; semantic soft fills communicate success, warning, locked, and pending states.

### Cards / Containers

- **Corner Style:** 3–6px for content cards; square for major sections and ledger summaries.
- **Background:** Paper on Campus Mist.
- **Shadow Strategy:** Flat at rest, using borders and top rules.
- **Border:** One-pixel Rule; course cards add a four-pixel navy top edge.
- **Internal Padding:** Usually 16–24px, increasing to 32px for primary work areas.

### Inputs / Fields

- **Style:** White field, one-pixel strong-gray stroke, 3px radius, and a 48px minimum height.
- **Focus:** Navy border plus a translucent gold focus ring.
- **Error / Disabled:** Semantic text and border treatment must remain legible without relying on color alone.

### Navigation

The top utility bar establishes university ownership. Main navigation is white and compact; the active destination uses a three-pixel gold underline. On phones, secondary identity text is removed before navigation wraps.

### Journey Rail

The public landing rail makes the product model tangible: Course, Exam, Grade, Result. It uses numbered navy markers on a gold path and becomes a compact grid on small screens.

## Do's and Don'ts

### Do:

- **Do** organize resources beneath a visible course code and title.
- **Do** use full-width page bands and ruled ledger structures for hierarchy.
- **Do** reserve real campus or classroom photography for public and authentication context.
- **Do** keep high-stakes exam controls visually stable and immediately legible.
- **Do** preserve accessible focus, contrast, reduced-motion, and responsive behavior.

### Don't:

- **Don't** introduce decorative gradients, glass panels, glowing decoration, or decorative blur; restrained photo-readability overlays are permitted.
- **Don't** build pages from repeated identical floating cards when a list, ledger, or ruled section communicates structure better.
- **Don't** use pills for ordinary labels, excessive rounding, or hover lift on every object.
- **Don't** add generic eyebrow copy above page headings.
- **Don't** use unlicensed imagery or fabricate an official university crest.

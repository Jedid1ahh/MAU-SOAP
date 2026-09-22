# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

MAU-SOAP serves three equally important university roles:

- Students accept course invitations, view enrolled courses, take available examinations, and check released results.
- Lecturers manage their assigned courses, invite and review enrolled Students, create examinations, supervise live sessions, grade submissions, and manage result release.
- Administrators manage accounts, create courses, and assign one Lecturer to each course.

## Product Purpose

MAU-SOAP is Modibbo Adama University's secure online assessment and course workspace. It brings course enrollment, examination delivery, live supervision, grading, and result access into a single role-aware portal.

Success means each person can sign in once, immediately understand their current academic tasks, and complete the correct workflow without redundant identity checks or confusion between roles and courses.

## Positioning

MAU-SOAP organizes the entire assessment lifecycle around assigned courses: Administrators establish course ownership, Lecturers manage the assessment workflow inside each course, and enrolled Students access only the examinations and results that belong to them.

## Operating Context

The system is used on desktop and mobile browsers in a Nigerian university context, including during time-sensitive examinations. Users may work with inconsistent network quality, so interfaces must remain clear, lightweight, and resilient without relying on decorative media for core tasks.

## Capabilities and Constraints

- Preserve all existing Flask routes, forms, CSRF behavior, authorization rules, JavaScript hooks, and backend logic.
- Maintain one shared Login flow that identifies the account role and redirects to the correct dashboard.
- Keep separate Student and Lecturer registration flows.
- Student accounts use the approved `student.mau.edu.ng` email domain.
- Students must be authenticated and enrolled in a course before accessing its examinations.
- A Lecturer may teach multiple courses; each course has only one assigned Lecturer at a time.
- Students may enroll in multiple courses after accepting invitations.
- Course resources, examinations, grades, and results remain separated by course.
- Frontend wording may be improved when its meaning and behavior remain unchanged.

## Brand Commitments

- Product name: MAU-SOAP.
- Institution: Modibbo Adama University.
- The interface must feel like a credible modern university system rather than a generic SaaS template.
- Admin, Lecturer, and Student experiences receive balanced visual importance.
- The supplied Edulearn and Kingster templates are craft references for education-focused hierarchy, real photography, and institutional presence; they are not to be copied directly.

## Evidence on Hand

- Existing Flask application, templates, tests, and route behavior in this repository.
- User-supplied screenshots showing layout imbalance on the Login and submission-confirmation pages.
- User-supplied links to Edulearn and Kingster education templates.
- No official MAU logo or institution-owned photography was supplied for this redesign.

## Product Principles

1. Course context is always visible.
2. Role clarity should never compete with the task at hand.
3. Examination states and next actions must be immediately scannable.
4. Institutional credibility comes from structure, typography, and real educational context—not ornamental interface effects.
5. Core workflows remain fast and usable under constrained connectivity.

## Accessibility & Inclusion

The web interface must support keyboard navigation, visible focus states, readable contrast, semantic forms and tables, reduced motion, touch-friendly controls, and responsive layouts down to small mobile screens.

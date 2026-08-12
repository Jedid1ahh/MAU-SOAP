# MAU-SOAP — Execution Specification

This document consolidates every functional requirement, non-functional requirement, and
behavioral detail the system is meant to implement, incorporating the original proposal's
requirements plus all revisions made during design review (server-side timing, OTP
verification, autosave/resume, duplicate-submission prevention, default Admin provisioning,
admin password reset,
manual grading of flagged responses, link-token security, and real-time admin alerting).

Each requirement is mapped to the specific tool(s) or library used to implement it, so this
document doubles as an implementation reference, not just a specification.

Treat this as the authoritative version — where it differs from Table 3.1 / 3.2 in the
original proposal document, this supersedes it.

---

## 1. Actors

| Actor | Description |
|---|---|
| **Admin** | The single default, pre-provisioned system administrator who logs in with configured credentials, creates and manages examinations, configures supervision, reviews submissions, grades flagged responses, and controls result release. The system provides no public Admin registration. |
| **Candidate** | Unregistered user who accesses a single examination via a unique link, verifies identity by an allowed-domain email address (OTP + magic link), and takes the exam under supervision. During development and testing the allowed domain is `@gmail.com`; it will be changed to `@mau.edu.ng` before final production use. |

---

## 2. Functional Requirements

| ID | Requirement | Description | Tools / Libraries |
|---|---|---|---|
| FR1 | Default Admin Provisioning | The system shall contain one default Admin account created during database initialization from securely configured credentials. No Admin registration route, form, or public account-creation workflow shall exist. | Flask-Bcrypt (password hashing), SQLAlchemy + PostgreSQL, environment variables/seed command |
| FR2 | Admin and Candidate Access Model | The pre-provisioned Admin uses a password-protected account and Flask session. Candidates require no account and access only a specific examination after email verification (see FR6). | Flask-Login (Admin sessions), SQLAlchemy |
| FR3 | Exam Creation | An Admin shall be able to create examinations containing multiple-choice, open-ended, and short-answer questions. | Flask, Jinja2 (admin forms/UI), SQLAlchemy + PostgreSQL |
| FR4 | Supervision Configuration | An Admin shall be able to configure, per examination, the time limit and webcam monitoring type (face or eye/gaze). The maximum warning count is a fixed system rule of 3 warnings. | Flask, SQLAlchemy (exam configuration columns) |
| FR5 | Exam Link Generation | The system shall generate a unique, cryptographically random shareable URL (≥128 bits entropy) for each examination, never exposing a sequential database identifier. | Python `secrets` module (CSPRNG token), SQLAlchemy (unique indexed column) |
| FR6 | Candidate Verification | A Candidate shall verify their identity by entering their name and an email address in the configured allowed domain, after which the system sends a one-time password (OTP) and a magic link to that email. The allowed domain shall be configurable through an environment variable: `@gmail.com` during development/testing and `@mau.edu.ng` before final production use. The Candidate gains exam access via either verification path, without a registered account. | Python `secrets` module (OTP + token generation), `hashlib`/`passlib` (token hashing before storage), Flask-Mail (SMTP delivery), environment-based configuration |
| FR7 | Copy-Paste Mitigation | The system shall prevent Candidates from copying examination text via keyboard shortcuts or right-click context menus during an active session. | Native browser Clipboard API, `keydown`/`contextmenu` event listeners (vanilla JS — no external library) |
| FR8 | Screenshot Detection | The system shall detect and log likely screenshot attempts (screen-capture keyboard shortcuts, window/tab focus loss) during an active session and issue a warning upon detection. Full OS-level prevention is not technically achievable in a browser context and is not claimed. | Native browser Page Visibility API, `keydown`/`blur` event listeners (vanilla JS — no external library) |
| FR9 | Webcam Monitoring | The system shall activate client-side webcam monitoring upon commencement of an examination. When a facial-presence or gaze-deviation violation is detected (per the configured monitor type), the system shall (a) warn the Candidate, (b) log the violation, and (c) alert the responsible Admin in near-real-time on the Admin dashboard. | MediaPipe Face Landmarker (MediaPipe Tasks Vision, JavaScript, client-side, WASM/WebGL), browser MediaDevices API (webcam access); AJAX polling (`fetch`) against a Flask endpoint for Admin-side alerts — see §4.4.1 |
| FR10 | Auto-Submission | The system shall automatically submit a Candidate's examination immediately when the warning count reaches 3. The third recorded warning therefore triggers auto-submission. | Vanilla JS (client-side trigger), Flask (server-side enforcement) |
| FR11 | Automatic Grading | The system shall automatically grade multiple-choice questions by exact match and short-answer questions via configurable case-sensitivity/space-tolerance string matching. Open-ended questions shall be recorded as pending and flagged for manual Admin review. | Python (Flask backend logic), SQLAlchemy |
| FR12 | Result Management | An Admin shall be able to view submitted responses and release results either immediately or at a scheduled date/time. Scheduled releases shall execute automatically via a server-side scheduled process, but a scheduled result shall remain withheld while any open-ended response in that submission is ungraded. Once grading is complete, the next scheduled release run may publish it. | Linux `cron` (scheduler), Flask (internal `/release-results` endpoint), Flask-Mail (optional release notification) |
| FR13 | Admin Password Reset | The pre-provisioned default Admin shall be able to request a password reset via the account's configured email and set a new password using a time-limited, single-use reset link. | Python `secrets` (token generation), Flask-Mail, Flask-Bcrypt (new password hashing) |
| FR14 | Manual Grading of Flagged Responses | An Admin shall be able to view Candidate responses to open-ended questions flagged for manual review and assign marks per question. A submission's result status shall move to "complete" once every question has been graded. | Flask, SQLAlchemy (`answer_grades` table) |
| FR15 | Session Logout | A logged-in Admin shall be able to log out, terminating their active session. | Flask-Login |
| FR16 | Exam Edit/Delete and Start Lock | An Admin shall be able to edit or delete an examination only while no Candidate has started it. As soon as the first Candidate starts the examination and a submission/session record with `started_at` is created, the examination is locked against structural editing and deletion, even if no Candidate has submitted a final response. | Flask, SQLAlchemy (started-submission guard before allowing edit/delete) |
| FR17 | Autosave & Resume | The system shall periodically persist a Candidate's in-progress responses during an active session and shall allow the Candidate to resume an interrupted session (e.g. after a disconnect or crash) without repeating email verification. | Vanilla JS (`fetch`, debounced interval), Flask endpoint, SQLAlchemy (JSONB `responses` column), browser `localStorage` (resume token) |
| FR18 | Server-Authoritative Timing | The system shall compute and enforce examination time limits server-side, based on a server-recorded start time, independent of any time value reported by the Candidate's browser. | Python `datetime` (server clock), Flask (elapsed-time calculation on every request) |
| FR19 | Duplicate Submission Prevention | The system shall permit at most one submission per Candidate per examination and shall reject any further response changes once a submission has been finalized. | PostgreSQL UNIQUE constraint (via SQLAlchemy), Flask enforcement logic |

---

## 3. Non-Functional Requirements

| ID | Category | Requirement | Tools / Libraries |
|---|---|---|---|
| NFR1 | Accessibility | The system shall be accessible via standard web browsers on desktop, laptop, and mobile devices without requiring installation of additional software. | HTML5, CSS3 (responsive layout) |
| NFR2 | Access Control | Admin access shall be limited to the pre-provisioned default Admin account; no public Admin registration endpoint shall exist. Candidate access shall be restricted to the configured allowed email domain (`gmail.com` during development/testing; `mau.edu.ng` for final production use). | Flask-Login, Python email-domain validation logic, environment-based configuration |
| NFR3 | Availability | The system shall remain available and responsive throughout the duration of any scheduled examination. | Gunicorn (production WSGI server), Nginx (reverse proxy), Let's Encrypt/Certbot (HTTPS/TLS) |
| NFR4 | Data Integrity | All examination data, candidate responses, warning logs, and results shall be stored securely with appropriate constraints and access controls. | PostgreSQL (ACID compliance), SQLAlchemy (FK/UNIQUE/NOT NULL constraints), `pg_dump` (backups) |
| NFR5 | Performance | The system shall respond to user inputs within an acceptable time frame for a smooth, uninterrupted examination experience. | Gunicorn (multi-worker), PostgreSQL indexing on high-traffic columns (`exam_link_token`, `candidate_email`) |
| NFR6 | Maintainability | The system shall be built using open-source technologies, documented sufficiently for future maintenance and extension by the university. | Git (version control); fully open-source stack throughout |
| NFR7 | Link Entropy | All exam links, verification links, and password-reset links shall use cryptographically random tokens of at least 128 bits of entropy and shall never expose sequential database identifiers. | Python `secrets` module |
| NFR8 | Token Lockout | The system shall lock a verification or password-reset token after 5 consecutive failed attempts, requiring a newly issued token to proceed. | Flask backend logic, SQLAlchemy `attempts` counter column |

---

## 4. Detailed System Behavior

### 4.1 Admin Authentication & Account Management
- The database initialization/seed process creates one default Admin account from environment-supplied email and password values; the password is stored only as a Flask-Bcrypt hash.
- No Admin registration page, route, API endpoint, or self-service account-creation workflow exists.
- Log in / log out (FR15).
- Request password reset: emailed time-limited single-use link (Python `secrets` + Flask-Mail); setting a new password invalidates the reset token (FR13).

### 4.2 Candidate Verification
- Candidate enters name + email at the exam link.
- The system validates the address against `CANDIDATE_EMAIL_DOMAIN`, configured as `gmail.com` during development/testing and changed to `mau.edu.ng` before final production use.
- The system generates a 6-digit OTP and a magic-link token (both hashed before storage via `secrets` + `hashlib`/`passlib`, both expiring after a short window), and sends them via Flask-Mail.
- Candidate verifies via either the OTP or the magic link.
- On success, the system creates (or resumes, per §4.5) the Candidate's submission record and issues a session/resume token — a second CSPRNG token distinct from the OTP — that authenticates the rest of the exam session so the Candidate is never asked to re-verify by email mid-session.
- Five consecutive failed OTP attempts locks the token; the Candidate must request a new one (NFR8).

### 4.3 Exam Management (Admin)
- Create an exam: title, course info, question list (MCQ / open-ended / short-answer), and supervision settings (time limit and monitor type). The warning limit is fixed system-wide at 3.
- Generate a unique, cryptographically random exam link on creation (FR5, NFR7).
- Edit or delete an exam only while no Candidate has started it. Creation of the first Candidate submission/session record and its server-side `started_at` value locks the exam immediately from structural edits and deletion (FR16).
- View submissions and control result release, immediate or scheduled (§4.6).

### 4.4 Exam-Taking Session (Candidate)
- On verified entry, the server records `started_at` and becomes the sole authority on remaining time; the client-side countdown is a display only, resynced periodically against the server (FR18).
- Copy-paste is blocked via the Clipboard API (FR7).
- Screenshot attempts are inferred from capture-related keyboard shortcuts and window/tab focus loss, logged and warned on — not silently blocked at the OS level, since no browser API can do that (FR8).
- Webcam monitoring runs entirely client-side via MediaPipe Face Landmarker, detecting face absence or gaze deviation depending on the configured monitor type. Raw video never leaves the device — only violation *events* are reported to the backend (FR9).
- **On a face-not-detected event specifically:** the Candidate sees an on-screen warning immediately; the event is written to the warning log with a timestamp; and the responsible Admin is alerted on the Admin dashboard without needing to wait until the exam ends (see §4.4.1).
- Each violation increments the Candidate's warning count; reaching 3 warnings triggers automatic submission immediately (FR10).
- Responses are autosaved periodically as the Candidate answers (FR17).

### 4.4.1 Admin-Side Live Alerting
- While an exam is in progress, the Admin dashboard polls a `/admin/exams/<id>/live-warnings` endpoint at a short interval (e.g. every 5–10 seconds) to surface new, unacknowledged violations per active Candidate — implemented with plain AJAX polling (`fetch`) rather than a persistent connection, to avoid adding infrastructure beyond the existing Flask stack.
- If true real-time push (rather than short-interval polling) is required later, this is the one place in the system where **Flask-SocketIO** (server) + **Socket.IO client** (browser) would be the natural upgrade — noted here as an optional enhancement, not a baseline requirement.

### 4.5 Disconnect & Resume
- If the Candidate's browser or connection drops mid-exam, reconnecting authenticates via the session/resume token issued at verification (§4.2) — no repeat email verification.
- The resume flow restores the last-saved responses, the server-computed remaining time, and the current warning count, so the Candidate continues rather than restarts (FR17).

### 4.6 Submission & Duplicate Prevention
- At most one submission exists per (exam, Candidate) pair, enforced at the database level.
- The submission/session record is created when the verified Candidate starts the examination; that start event also locks the examination from structural editing and deletion.
- Once a submission is finalized (manual or auto-submit), it is locked — no further response changes are accepted (FR19).

### 4.7 Grading
- MCQ: graded by exact match against the correct option's key.
- Short-answer: graded via string matching with configurable case-sensitivity and leading/trailing-space tolerance.
- Open-ended: not auto-graded; recorded as pending and surfaced to the Admin for manual review (FR11).
- A submission's overall result is marked "complete" once every question has an assigned mark; until then it is "pending manual review" (FR14).

### 4.8 Results
- Stored per submission with score, marks obtained, and total marks.
- Released either immediately on submission or at an Admin-scheduled date/time.
- Scheduled release is executed automatically by a cron job hitting an internal endpoint — no manual Admin action is required at release time (FR12).
- Before releasing a scheduled result, the server confirms that the submission's result status is `complete`. If any open-ended response remains ungraded, the result stays withheld and is reconsidered by the next scheduled release run after grading is completed.
- Candidates can view their result only once it has been released.

---

## 5. Supporting Development & Infrastructure Tools

Tools that support the system as a whole rather than a single requirement:

| Tool | Purpose |
|---|---|
| Git | Version control, source collaboration |
| VS Code | Primary code editor |
| pgAdmin 4 | PostgreSQL database GUI/administration |
| Postman | Manual API endpoint testing during development |
| pytest | Automated unit testing (grading logic, matching rules, token validation) |
| Gunicorn | Production-grade WSGI server (Flask's built-in dev server is not suitable for live deployment) |
| Nginx | Reverse proxy in front of Gunicorn; TLS termination |
| Let's Encrypt / Certbot | Free TLS certificate issuance for HTTPS |

---

## 6. Out of Scope

Consistent with the original proposal's scope boundary — the following are explicitly **not** part of this system:
- Advanced biometric authentication (beyond institutional-email OTP verification)
- Integration with MAU's existing student information system
- Payment processing
- Native mobile application development

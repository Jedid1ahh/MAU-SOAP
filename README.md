# MAU-SOAP

MAU-SOAP is the Modibbo Adama University browser-based secure online
assessment and supervision platform. The application currently includes the
verified functionality from Phases 1–13, including course-centered Admin,
Lecturer, and Student portals.

## Current capabilities

- One pre-provisioned Admin account for accounts, course creation, and
  Lecturer assignment; no Admin registration
- Lecturer registration with exact `@mau.edu.ng` validation, email
  verification, and Admin approval
- Student registration with exact `@student.mau.edu.ng` validation
- Role-isolated Admin, Lecturer, and Student dashboards
- Admin-created courses assigned to exactly one Lecturer at a time, with full
  workspace transfer on reassignment
- Lecturer-owned examination/question management, live supervision, grading,
  and result release, isolated by assigned course
- Registered-Student invitations, acceptance, enrollment, and course rosters
- Secure examination links with OTP and magic-link verification
- Server-authoritative timing, autosave/resume, supervision warnings, and
  third-warning auto-submission
- Automatic and manual grading
- Immediate and scheduled result release, with ungraded open-ended results
  withheld
- Student examinations, attempts, and results grouped by enrolled course
- Exam-link verification restricted to registered Students who accepted that
  course's invitation

A full assignment-resource workflow is not yet implemented; the current
course workspace covers invitations, enrollments, examinations, grading, and
results.

## Project structure

```text
MAU-SOAP/
├── app/
│   ├── accounts/       # Lecturer/Student registration and login
│   ├── admin/          # Admin authentication and system oversight
│   ├── api/            # JSON health and session endpoints
│   ├── candidate/      # Secure examination-link flow
│   ├── lecturer/       # Lecturer portal
│   ├── student/        # Student portal and result access
│   ├── models/         # SQLAlchemy models
│   ├── static/         # CSS, JavaScript, and MediaPipe assets
│   └── templates/      # Shared Jinja templates
├── docs/specifications/# Requirements and phase roadmap
├── migrations/         # Alembic database migrations
├── tests/              # Automated tests
├── requirements.txt    # Runtime dependencies
├── requirements-dev.txt# Development dependencies
└── wsgi.py             # Flask/Gunicorn entry point
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
python -m flask db upgrade
python -m flask seed-db
python -m flask run
```

On Git Bash for Windows, activate with `source .venv/Scripts/activate`.

The default `.env.example` database URL targets local XAMPP/MariaDB. Replace
all placeholder secrets in the private `.env` before running the system.

When upgrading from Phase 11, the migration preserves every existing exam by
creating an unassigned legacy course for each existing course code. After the
upgrade, log in as Admin and assign those courses to approved Lecturers; the
complete exam workspace transfers with the assignment.

## Verification

```bash
python -m pytest
python -m ruff check .
python -m flask db check
git diff --check
```

## Branch strategy

- `main` contains verified phase milestones.
- `develop` is available for integration work.
- `feature/<short-name>` branches contain focused changes.

Never commit `.env`, `.venv`, database data, supervision evidence, `.agents`,
`.codex`, or `skills-lock.json`.

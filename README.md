# MAU-SOAP

MAU-SOAP is the Modibbo Adama University browser-based secure online
assessment and supervision platform. The application currently includes the
verified functionality from Phases 1–10 plus the Phase 11 multi-role account
foundation.

## Current capabilities

- One pre-provisioned Admin account; no Admin registration
- Lecturer registration with exact `@mau.edu.ng` validation, email
  verification, and Admin approval
- Student registration with exact `@student.mau.edu.ng` validation
- Role-isolated Admin, Lecturer, and Student dashboards
- Examination and question management
- Secure examination links with OTP and magic-link verification
- Server-authoritative timing, autosave/resume, supervision warnings, and
  third-warning auto-submission
- Automatic and manual grading
- Immediate and scheduled result release, with ungraded open-ended results
  withheld
- Student examination history and protected result access

The existing examination-link flow remains operational while the Lecturer and
Student dashboards are expanded in Phases 12 and 13.

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

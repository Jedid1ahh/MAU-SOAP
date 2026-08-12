# MAU-SOAP

MAU-SOAP is the Modibbo Adama University browser-based examination and
supervision platform. This repository currently contains **Phase 1**: a clean,
tested Flask application foundation with PostgreSQL connectivity.

## Phase 1 contents

- Flask application factory
- Separate `main`, `admin`, `candidate`, and `api` blueprints
- Environment-based configuration and secret handling
- PostgreSQL development service through Docker Compose
- Reusable Flask extensions, initialized without circular imports
- Application and database health endpoints
- Unit tests for configuration, routing, and database connectivity
- Git-ready ignore rules and documented branch strategy

Feature logic such as authentication, exam management, verification, exam
sessions, and grading belongs to later phases and is deliberately absent.

## Project structure

```text
MAU-SOAP/
├── app/
│   ├── admin/          # Admin routes (features begin in Phase 3)
│   ├── api/            # JSON endpoints and health checks
│   ├── candidate/      # Candidate routes (features begin in Phase 5)
│   ├── main/           # Public landing page
│   ├── static/         # CSS and later browser-side assets
│   ├── templates/      # Shared Jinja templates
│   ├── __init__.py     # Application factory
│   ├── config.py       # Environment-specific settings
│   └── extensions.py   # Unbound Flask extensions
├── docs/               # Phase-specific setup and testing instructions
│   └── specifications/ # Approved Execution.md and Phases.md source of truth
├── tests/              # Automated unit tests
├── compose.yaml        # Local PostgreSQL 16 service
├── requirements.txt    # Runtime dependencies
├── requirements-dev.txt# Testing/development dependencies
└── wsgi.py             # Flask/Gunicorn entry point
```

## Quick start

Detailed Windows, macOS, and Linux instructions are in
[`docs/PHASE_1_TESTING.md`](docs/PHASE_1_TESTING.md).

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d db
flask run
```

Open <http://127.0.0.1:5000> and verify the database at
<http://127.0.0.1:5000/api/v1/health/database>.

Run all Phase 1 checks with:

```bash
pytest
ruff check .
```

## Branch strategy

- `main` contains verified phase milestones.
- `develop` is the integration branch for the next phase.
- `feature/<short-name>` branches contain focused changes and merge into
  `develop` after their tests pass.

No secret, `.env` file, virtual environment, database volume, or generated test
artifact should be committed.

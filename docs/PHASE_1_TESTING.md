# Phase 1 setup and testing guide

This guide verifies the environment, Flask application, blueprint structure,
configuration safety, and PostgreSQL connection delivered in Phase 1.

## 1. Install prerequisites

Install:

- Python 3.10 or newer
- Git
- Docker Desktop (Windows/macOS) or Docker Engine with Compose (Linux)
- VS Code (recommended, not required)

Confirm the command-line tools:

```bash
python --version
git --version
docker --version
docker compose version
```

On Windows, use PowerShell. If `python` is unavailable but the Python launcher
is installed, substitute `py` for `python` in every command.

## 2. Create and activate a virtual environment

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements-dev.txt
```

If PowerShell blocks activation for the current window, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## 3. Create the local configuration

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### macOS/Linux

```bash
cp .env.example .env
```

Open `.env` and replace both password placeholders with the same local database
password. Replace `SECRET_KEY` with a random value. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not commit or share `.env`.

## 4. Start PostgreSQL

```bash
docker compose up -d db
docker compose ps
```

Wait until the service reports `healthy`. If port 5432 is already occupied by
another PostgreSQL installation, either stop that installation or update both
the host port in `compose.yaml` and the port in `DATABASE_URL`.

## 5. Run the unit tests

```bash
pytest
```

Expected result: all Phase 1 tests pass and the coverage report shows coverage
for the application factory, configuration, and health routes.

Run the style/static check separately:

```bash
ruff check .
```

Expected result: `All checks passed!`

## 6. Start and inspect the Flask application

```bash
flask run
```

Visit these URLs:

| URL | Expected result |
|---|---|
| <http://127.0.0.1:5000/> | MAU-SOAP Phase 1 landing page |
| <http://127.0.0.1:5000/admin/> | Admin blueprint placeholder |
| <http://127.0.0.1:5000/exam/> | Candidate blueprint placeholder |
| <http://127.0.0.1:5000/api/v1/health> | JSON with `status: ok` |
| <http://127.0.0.1:5000/api/v1/health/database> | JSON with `database: connected` |

You can also test both API checks in PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/v1/health
Invoke-RestMethod http://127.0.0.1:5000/api/v1/health/database
```

Or with curl:

```bash
curl http://127.0.0.1:5000/api/v1/health
curl http://127.0.0.1:5000/api/v1/health/database
```

Stop Flask with `Ctrl+C`.

## 7. Confirm configuration failure is clear

Temporarily rename `.env`, then run `flask run`. The app should stop immediately
with a message identifying missing `SECRET_KEY` and/or
`SQLALCHEMY_DATABASE_URI`. Restore `.env` before continuing.

This proves that the application does not silently run with missing secrets.

## 8. Initialize the Git workflow

The repository is initialized on `main`. After confirming all checks pass:

```bash
git status
git add .
git commit -m "Complete Phase 1 project foundation"
git branch develop
git switch develop
```

Future work should use a focused branch such as
`feature/phase-2-database-schema`, created from `develop`.

## 9. Stop local services

Stop PostgreSQL without deleting its data:

```bash
docker compose stop
```

Use `docker compose down` only when you want to remove the container and
network. Do not add `--volumes` unless you intentionally want to delete the
local development database.


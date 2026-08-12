"""HTTP behavior tests for all Phase 1 endpoints."""

from sqlalchemy.exc import OperationalError

from app.extensions import db


def test_landing_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"MAU-SOAP" in response.data
    assert b"Phase 1 running" in response.data


def test_admin_placeholder(client):
    response = client.get("/admin/")

    assert response.status_code == 200
    assert b"Admin area" in response.data


def test_candidate_placeholder(client):
    response = client.get("/exam/")

    assert response.status_code == 200
    assert b"Candidate area" in response.data


def test_service_health(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.get_json() == {"service": "mau-soap", "status": "ok"}


def test_database_health_success(client):
    response = client.get("/api/v1/health/database")

    assert response.status_code == 200
    assert response.get_json() == {"database": "connected", "status": "ok"}


def test_database_health_failure_returns_safe_response(client, monkeypatch):
    """Driver details must never be exposed when the database is unavailable."""

    def fail_query(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, RuntimeError("private driver detail"))

    monkeypatch.setattr(db.session, "execute", fail_query)
    response = client.get("/api/v1/health/database")

    assert response.status_code == 503
    assert response.get_json() == {"database": "unavailable", "status": "error"}
    assert b"private driver detail" not in response.data


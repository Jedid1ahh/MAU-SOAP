"""Unit tests for application creation and configuration."""

import pytest

from app import create_app
from app.config import _as_bool, _database_url, validate_configuration
from app.extensions import db


def test_factory_uses_testing_configuration(app):
    """The testing configuration must be isolated and deterministic."""

    assert app.testing is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite+pysqlite:///:memory:"
    assert app.config["CANDIDATE_EMAIL_DOMAIN"] == "gmail.com"


def test_factory_registers_required_blueprints(app):
    """Every Phase 1 route group must be available."""

    assert {"main", "admin", "candidate", "api"} <= set(app.blueprints)


def test_database_extension_is_bound_to_app(app):
    """Flask-SQLAlchemy must be initialized by the factory."""

    assert "sqlalchemy" in app.extensions
    assert app.extensions["sqlalchemy"] is db


def test_factory_rejects_unknown_configuration():
    """Typos in FLASK_CONFIG should produce a helpful error."""

    with pytest.raises(ValueError, match="Unknown FLASK_CONFIG"):
        create_app("not-a-real-environment")


def test_factory_rejects_domain_with_at_symbol():
    """The configured domain is stored without an @ prefix."""

    with pytest.raises(RuntimeError, match="bare domain"):
        create_app("testing", {"CANDIDATE_EMAIL_DOMAIN": "@gmail.com"})


def test_configuration_rejects_missing_required_values():
    """Startup validation should name every missing required setting."""

    with pytest.raises(
        RuntimeError,
        match="SECRET_KEY, SQLALCHEMY_DATABASE_URI",
    ):
        validate_configuration(
            {
                "SECRET_KEY": None,
                "SQLALCHEMY_DATABASE_URI": None,
                "CANDIDATE_EMAIL_DOMAIN": "gmail.com",
            }
        )


@pytest.mark.parametrize(
    ("environment_value", "expected"),
    [("true", True), ("YES", True), ("0", False), ("off", False)],
)
def test_boolean_environment_values(monkeypatch, environment_value, expected):
    """Boolean environment settings should accept common spellings."""

    monkeypatch.setenv("MAU_SOAP_TEST_BOOLEAN", environment_value)

    assert _as_bool("MAU_SOAP_TEST_BOOLEAN") is expected


def test_boolean_environment_value_uses_default_when_missing(monkeypatch):
    """An absent optional boolean should return its documented default."""

    monkeypatch.delenv("MAU_SOAP_TEST_BOOLEAN", raising=False)

    assert _as_bool("MAU_SOAP_TEST_BOOLEAN", default=True) is True


@pytest.mark.parametrize(
    ("configured_url", "expected_url"),
    [
        (
            "postgres://user:password@localhost/database",
            "postgresql+psycopg://user:password@localhost/database",
        ),
        (
            "postgresql://user:password@localhost/database",
            "postgresql+psycopg://user:password@localhost/database",
        ),
        (
            "postgresql+psycopg://user:password@localhost/database",
            "postgresql+psycopg://user:password@localhost/database",
        ),
    ],
)
def test_database_url_normalization(monkeypatch, configured_url, expected_url):
    """Legacy PostgreSQL URLs should be normalized for Psycopg 3."""

    monkeypatch.setenv("DATABASE_URL", configured_url)

    assert _database_url() == expected_url


def test_database_url_can_be_absent(monkeypatch):
    """Missing DATABASE_URL is reported later by configuration validation."""

    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert _database_url() is None

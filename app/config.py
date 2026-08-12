"""Environment-aware configuration for MAU-SOAP.

Only non-sensitive defaults live in source control. Required secrets and the
database connection string are supplied through environment variables.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


def _as_bool(variable_name: str, default: bool = False) -> bool:
    """Read a conventional true/false environment variable safely."""

    raw_value = os.getenv(variable_name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str | None:
    """Return a SQLAlchemy 2 compatible database URL when configured."""

    url = os.getenv("DATABASE_URL")
    if not url:
        return None

    # Some hosts still provide the legacy postgres:// form. Psycopg 3 uses the
    # explicit postgresql+psycopg:// SQLAlchemy dialect.
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class BaseConfig:
    """Settings shared by every environment."""

    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CANDIDATE_EMAIL_DOMAIN = os.getenv("CANDIDATE_EMAIL_DOMAIN", "gmail.com")

    # The idempotent ``flask seed-db`` command consumes these values. They are
    # intentionally not given insecure source-code defaults.
    DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL")
    DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD")
    SEED_DUMMY_EXAM = _as_bool("SEED_DUMMY_EXAM", default=True)

    MAIL_SERVER = os.getenv("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "25"))
    MAIL_USE_TLS = _as_bool("MAIL_USE_TLS")
    MAIL_USE_SSL = _as_bool("MAIL_USE_SSL")
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")
    MAIL_SUPPRESS_SEND = _as_bool("MAIL_SUPPRESS_SEND")

    JSON_SORT_KEYS = False


class DevelopmentConfig(BaseConfig):
    """Local developer settings."""

    DEBUG = True


class TestingConfig(BaseConfig):
    """Fast, isolated defaults used only by pytest."""

    TESTING = True
    SECRET_KEY = "phase-1-test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///:memory:"
    MAIL_SUPPRESS_SEND = True


class ProductionConfig(BaseConfig):
    """Security-oriented defaults for the future production deployment."""

    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def validate_configuration(config: Mapping[str, Any]) -> None:
    """Fail early when a required setting is missing or unsafe.

    A clear startup error is easier to diagnose than a cryptic failure during a
    request. Tests use their own safe in-memory values.
    """

    missing = [
        setting
        for setting in ("SECRET_KEY", "SQLALCHEMY_DATABASE_URI")
        if not config.get(setting)
    ]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Missing required configuration: {names}. "
            "Copy .env.example to .env and provide real values."
        )

    domain = str(config.get("CANDIDATE_EMAIL_DOMAIN", "")).strip()
    if not domain or "@" in domain:
        raise RuntimeError(
            "CANDIDATE_EMAIL_DOMAIN must be a bare domain such as gmail.com."
        )


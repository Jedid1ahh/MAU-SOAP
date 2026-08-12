"""Shared pytest fixtures for the MAU-SOAP test suite."""

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    """Create a fresh isolated Flask application for each test."""

    application = create_app(
        "testing",
        {
            "DEFAULT_ADMIN_EMAIL": "admin@mau.edu.ng",
            "DEFAULT_ADMIN_PASSWORD": "Phase2TestPassword!",
            "SEED_DUMMY_EXAM": True,
        },
    )

    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    """Provide Flask's HTTP test client."""

    return app.test_client()
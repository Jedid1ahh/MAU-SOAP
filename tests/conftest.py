"""Shared pytest fixtures for the MAU-SOAP test suite."""

import pytest

from app import create_app


@pytest.fixture()
def app():
    """Create a fresh isolated Flask application for each test."""

    return create_app("testing")


@pytest.fixture()
def client(app):
    """Provide Flask's HTTP test client."""

    return app.test_client()


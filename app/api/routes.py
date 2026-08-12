"""Phase 1 service and database health endpoints."""

from flask import current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

from . import api_bp


@api_bp.get("/health")
def health():
    """Report that the Flask process can accept requests."""

    return jsonify(service="mau-soap", status="ok"), 200


@api_bp.get("/health/database")
def database_health():
    """Execute a minimal query to prove that the configured database responds."""

    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Avoid returning driver details or credentials to the caller. Full
        # diagnostics are written to the server log for the developer.
        db.session.rollback()
        current_app.logger.exception("Database health check failed")
        return jsonify(database="unavailable", status="error"), 503

    return jsonify(database="connected", status="ok"), 200


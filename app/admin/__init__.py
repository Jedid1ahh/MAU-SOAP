"""Admin blueprint package."""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__)

from . import (  # noqa: E402, F401
    exam_routes,
    grading_routes,
    routes,
    supervision_routes,
)
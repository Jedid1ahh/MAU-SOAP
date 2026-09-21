"""Lecturer portal blueprint."""

from flask import Blueprint

lecturer_bp = Blueprint("lecturer", __name__)

from app.admin import (  # noqa: E402, F401
    exam_routes,
    grading_routes,
    result_routes,
    supervision_routes,
)

from . import routes  # noqa: E402, F401

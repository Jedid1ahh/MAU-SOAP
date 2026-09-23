"""Lecturer portal blueprint."""

from flask import Blueprint

lecturer_bp = Blueprint("lecturer", __name__)

from app.admin import (  # noqa: E402, F401
    exam_routes,
    grading_routes,
    result_routes,
    supervision_routes,
)

from . import (  # noqa: E402
    coursework_routes,  # noqa: E402, F401
    question_bank_routes,  # noqa: E402, F401
    routes,  # noqa: E402, F401
)

"""Student portal blueprint."""

from flask import Blueprint

student_bp = Blueprint("student", __name__)

from . import routes  # noqa: E402, F401

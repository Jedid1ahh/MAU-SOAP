"""Lecturer portal blueprint."""

from flask import Blueprint

lecturer_bp = Blueprint("lecturer", __name__)

from . import routes  # noqa: E402, F401

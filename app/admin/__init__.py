"""Admin blueprint package."""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__)

from . import (  # noqa: E402, F401
    account_routes,
    course_routes,
    routes,
)

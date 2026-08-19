"""Admin blueprint package."""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__)

from . import exam_routes, routes, supervision_routes  # noqa: E402, F401
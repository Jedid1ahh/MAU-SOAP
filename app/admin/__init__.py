"""Admin blueprint package."""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__)

from . import routes  # noqa: E402, F401  (register routes after blueprint creation)


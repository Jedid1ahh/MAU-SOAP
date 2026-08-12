"""Candidate blueprint package."""

from flask import Blueprint

candidate_bp = Blueprint("candidate", __name__)

from . import routes  # noqa: E402, F401  (register routes after blueprint creation)


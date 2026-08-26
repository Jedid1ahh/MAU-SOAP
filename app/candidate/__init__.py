"""Candidate blueprint package."""

from flask import Blueprint

candidate_bp = Blueprint("candidate", __name__)

from . import result_routes, routes, session_routes  # noqa: E402, F401
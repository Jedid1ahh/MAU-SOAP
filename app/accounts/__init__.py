"""Lecturer and Student account blueprint."""

from flask import Blueprint

accounts_bp = Blueprint("accounts", __name__)

from . import routes  # noqa: E402, F401

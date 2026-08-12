"""Public routes available before authentication."""

from flask import render_template

from . import main_bp


@main_bp.get("/")
def index():
    """Render the Phase 1 landing page."""

    return render_template("index.html")


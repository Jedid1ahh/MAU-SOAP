"""Phase 1 placeholder routes for the future Admin area."""

from flask import render_template

from . import admin_bp


@admin_bp.get("/")
def index():
    """Confirm that the Admin blueprint is registered correctly."""

    return render_template(
        "placeholder.html",
        page_title="Admin area",
        message="Admin authentication will be implemented in Phase 3.",
    )


"""Phase 1 placeholder routes for the future Candidate area."""

from flask import render_template

from . import candidate_bp


@candidate_bp.get("/")
def index():
    """Confirm that the Candidate blueprint is registered correctly."""

    return render_template(
        "placeholder.html",
        page_title="Candidate area",
        message="Candidate examination access will be implemented in Phase 5.",
    )


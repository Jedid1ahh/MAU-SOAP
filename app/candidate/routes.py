"""Public examination-link routes awaiting Phase 5 verification."""

from flask import abort, render_template
from sqlalchemy import select

from app.extensions import db
from app.models import Exam

from . import candidate_bp


@candidate_bp.get("/")
def index():
    """Confirm that the Candidate blueprint is registered correctly."""

    return render_template(
        "placeholder.html",
        page_title="Candidate area",
        message="Candidate examination access will be implemented in Phase 5.",
    )


@candidate_bp.get("/<token>")
def exam_landing(token: str):
    """Resolve a cryptographic exam link without exposing its database ID."""

    exam = db.session.scalar(
        select(Exam).where(Exam.exam_link_token == token)
    )

    if exam is None:
        abort(404)

    return render_template(
        "candidate/exam_landing.html",
        exam=exam,
    )
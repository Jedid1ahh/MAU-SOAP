"""Authenticated Student entry routes for course examinations."""

from __future__ import annotations

from flask import abort, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy import select

from app.access import role_required
from app.extensions import db
from app.models import Exam, Role

from . import candidate_bp
from .session_services import (
    finalize_expired_submission,
    student_can_access_exam,
    submission_for_student,
)


def _exam_by_token(token: str) -> Exam:
    """Resolve a CSPRNG examination token or return HTTP 404."""

    exam = db.session.scalar(select(Exam).where(Exam.exam_link_token == token))
    if exam is None:
        abort(404)
    return exam


def _require_enrollment(exam: Exam) -> None:
    """Reject Students who have not accepted this course invitation."""

    if not student_can_access_exam(exam, current_user):
        abort(403)


@candidate_bp.get("/")
@role_required(Role.STUDENT)
def index():
    """Send an authenticated Student to their course dashboard."""

    return redirect(url_for("student.index"))


@candidate_bp.get("/<token>")
@role_required(Role.STUDENT)
def exam_landing(token: str):
    """Resume an existing attempt; new attempts start from the dashboard."""

    exam = _exam_by_token(token)
    _require_enrollment(exam)
    submission = submission_for_student(exam, current_user)

    if submission is None:
        flash(
            "Open the examination from your Student dashboard to begin.",
            "info",
        )
        return redirect(url_for("student.index"))

    if submission.is_finalized or finalize_expired_submission(submission):
        db.session.commit()
        return redirect(
            url_for("candidate.submission_received", token=exam.exam_link_token)
        )

    return redirect(url_for("candidate.exam_session", token=exam.exam_link_token))


@candidate_bp.get("/<token>/ready")
@role_required(Role.STUDENT)
def exam_ready(token: str):
    """Keep old ready-page links safe while using direct authenticated entry."""

    return exam_landing(token)


@candidate_bp.get("/<token>/verify")
@candidate_bp.get("/<token>/verify/<magic_token>")
@role_required(Role.STUDENT)
def retired_verification(token: str, magic_token: str | None = None):
    """Retire the former per-exam OTP and magic-link verification routes."""

    _exam_by_token(token)
    flash(
        "Examination email verification is no longer required. "
        "Open the examination from your Student dashboard.",
        "info",
    )
    return redirect(url_for("student.index"))

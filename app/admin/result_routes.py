"""Lecturer result oversight and early-release routes."""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.grading import grade_submission
from app.lecturer import lecturer_bp
from app.lecturer.auth import lecturer_required
from app.models import AnswerGrade, Exam, Submission
from app.result_release import (
    ResultNotCompleteError,
    release_result_now,
    synchronize_result_release,
)


def _owned_finalized_submission(submission_id: int) -> Submission:
    """Load one finalized result belonging to the authenticated Lecturer."""

    submission = db.session.scalar(
        select(Submission)
        .join(Exam)
        .where(
            Submission.id == submission_id,
            Submission.submitted_at.is_not(None),
            Exam.admin_id == current_user.id,
        )
        .options(
            selectinload(Submission.exam).selectinload(Exam.questions),
            selectinload(Submission.answer_grades).selectinload(
                AnswerGrade.question
            ),
            selectinload(Submission.result),
        )
    )
    if submission is None:
        abort(404)

    return submission


@lecturer_bp.get("/results")
@lecturer_required
def results_overview():
    """List grading and release state for all owned finalized attempts."""

    submissions = db.session.scalars(
        select(Submission)
        .join(Exam)
        .where(
            Submission.submitted_at.is_not(None),
            Exam.admin_id == current_user.id,
        )
        .options(
            selectinload(Submission.exam).selectinload(Exam.questions),
            selectinload(Submission.answer_grades).selectinload(
                AnswerGrade.question
            ),
            selectinload(Submission.result),
        )
        .order_by(Submission.submitted_at.desc())
    ).all()

    for submission in submissions:
        result = grade_submission(submission)
        synchronize_result_release(result)

    db.session.commit()

    return render_template(
        "admin/results_overview.html",
        submissions=submissions,
    )


@lecturer_bp.post("/results/<int:submission_id>/release")
@lecturer_required
def release_result(submission_id: int):
    """Release one completed scheduled result before its configured time."""

    submission = _owned_finalized_submission(submission_id)
    result = grade_submission(submission)

    try:
        release_result_now(result)
    except ResultNotCompleteError as error:
        db.session.rollback()
        flash(str(error), "error")
    else:
        db.session.commit()
        flash("Candidate result released.", "success")

    return redirect(url_for("lecturer.results_overview"))

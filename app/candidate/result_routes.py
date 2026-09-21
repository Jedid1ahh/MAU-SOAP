"""Secure Candidate result access and release-status routes."""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import select

from app.access import role_required
from app.extensions import db
from app.grading import grade_submission
from app.models import Exam, ResultStatus, Role
from app.result_release import synchronize_result_release

from . import candidate_bp
from .session_services import student_can_access_exam, submission_for_student


def _exam_by_token(token: str) -> Exam | None:
    return db.session.scalar(
        select(Exam).where(Exam.exam_link_token == token)
    )


@candidate_bp.get("/<token>/result")
@role_required(Role.STUDENT)
def candidate_result(token: str):
    """Show a released result only to its enrolled, logged-in Student."""

    exam = _exam_by_token(token)
    if exam is None:
        abort(404)

    if not student_can_access_exam(exam, current_user):
        abort(403)
    submission = submission_for_student(exam, current_user)
    if submission is None or not submission.is_finalized:
        flash("Candidate result access could not be verified.", "error")
        return redirect(url_for("candidate.exam_landing", token=token))

    result = grade_submission(submission)
    synchronize_result_release(result)
    db.session.commit()

    if not result.is_released:
        return render_template(
            "candidate/result_pending.html",
            exam=exam,
            submission=submission,
            result=result,
            awaiting_manual_review=(
                result.status is ResultStatus.PENDING_MANUAL_REVIEW
            ),
        )

    grades_by_question = {
        grade.question_id: grade for grade in submission.answer_grades
    }
    result_rows = [
        {
            "question": question,
            "response": (submission.responses or {}).get(
                str(question.id),
                "",
            ),
            "grade": grades_by_question[question.id],
        }
        for question in exam.questions
    ]
    return render_template(
        "candidate/result.html",
        exam=exam,
        submission=submission,
        result=result,
        result_rows=result_rows,
    )

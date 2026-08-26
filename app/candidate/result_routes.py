"""Secure Candidate result access and release-status routes."""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, session, url_for
from sqlalchemy import select

from app.extensions import db
from app.grading import grade_submission
from app.models import Exam, ResultStatus
from app.result_release import synchronize_result_release

from . import candidate_bp
from .session_services import resolve_submission_session


def _access_session_key(exam: Exam) -> str:
    return f"candidate_access_token_{exam.id}"


def _exam_by_token(token: str) -> Exam | None:
    return db.session.scalar(
        select(Exam).where(Exam.exam_link_token == token)
    )


@candidate_bp.get("/<token>/result")
def candidate_result(token: str):
    """Show a released result only to its matching Candidate session."""

    exam = _exam_by_token(token)
    if exam is None:
        abort(404)

    raw_token = session.get(_access_session_key(exam))
    submission = resolve_submission_session(
        exam,
        raw_token if isinstance(raw_token, str) else None,
    )
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
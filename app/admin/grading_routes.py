"""Phase 9 Admin automatic and manual grading routes."""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.grading import (
    InvalidManualGradeError,
    assign_manual_grade,
    grade_submission,
)
from app.models import (
    AnswerGrade,
    Exam,
    QuestionType,
    ResultStatus,
    Submission,
)

from . import admin_bp
from .auth import admin_required
from .grading_forms import ManualGradeForm


def _owned_submission(submission_id: int) -> Submission:
    """Load one finalized submission owned by the authenticated Admin."""

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


def _grading_rows(submission: Submission) -> list[dict]:
    """Order grade records alongside the Candidate's stored responses."""

    grades_by_question = {
        grade.question_id: grade for grade in submission.answer_grades
    }
    return [
        {
            "question": question,
            "grade": grades_by_question[question.id],
            "response": (submission.responses or {}).get(
                str(question.id),
                "",
            ),
        }
        for question in submission.exam.questions
    ]


def _render_submission(
    submission: Submission,
    form: ManualGradeForm,
    *,
    target_grade_id: int | None = None,
    status_code: int = 200,
):
    """Render one grading workspace with optional field errors."""

    return (
        render_template(
            "admin/submission_grading.html",
            submission=submission,
            exam=submission.exam,
            result=submission.result,
            grading_rows=_grading_rows(submission),
            form=form,
            target_grade_id=target_grade_id,
        ),
        status_code,
    )


@admin_bp.get("/grading")
@admin_required
def grading_queue():
    """List finalized submissions still awaiting manual review."""

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
        .order_by(Submission.submitted_at.asc())
    ).all()

    for submission in submissions:
        grade_submission(submission)
    db.session.commit()

    pending_submissions = [
        submission
        for submission in submissions
        if submission.result.status is ResultStatus.PENDING_MANUAL_REVIEW
    ]
    pending_counts = {
        submission.id: sum(
            grade.awarded_marks is None
            for grade in submission.answer_grades
        )
        for submission in pending_submissions
    }
    return render_template(
        "admin/grading_queue.html",
        submissions=pending_submissions,
        pending_counts=pending_counts,
    )


@admin_bp.get("/grading/submissions/<int:submission_id>")
@admin_required
def grade_submission_view(submission_id: int):
    """Show every response and its current grading state."""

    submission = _owned_submission(submission_id)
    grade_submission(submission)
    db.session.commit()
    return _render_submission(
        submission,
        ManualGradeForm(),
    )


@admin_bp.post(
    "/grading/submissions/<int:submission_id>/answers/<int:grade_id>"
)
@admin_required
def grade_open_answer(submission_id: int, grade_id: int):
    """Assign marks to one pending open-ended response."""

    submission = _owned_submission(submission_id)
    grade_submission(submission)
    grade = next(
        (
            item
            for item in submission.answer_grades
            if item.id == grade_id
        ),
        None,
    )
    if grade is None:
        abort(404)
    if grade.question.question_type is not QuestionType.OPEN_ENDED:
        abort(404)

    form = ManualGradeForm()
    if form.validate_on_submit():
        try:
            assign_manual_grade(
                grade,
                form.awarded_marks.data,
                current_user,
                form.feedback.data,
            )
        except InvalidManualGradeError as error:
            form.awarded_marks.errors.append(str(error))
        else:
            db.session.commit()
            flash("Open-ended response graded.", "success")
            return redirect(
                url_for(
                    "admin.grade_submission_view",
                    submission_id=submission.id,
                )
            )

    db.session.rollback()
    submission = _owned_submission(submission_id)
    grade_submission(submission)
    return _render_submission(
        submission,
        form,
        target_grade_id=grade_id,
        status_code=400,
    )
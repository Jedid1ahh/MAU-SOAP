"""Student dashboard and result routes."""

from flask import abort, render_template
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.access import role_required
from app.extensions import db
from app.grading import grade_submission
from app.models import AnswerGrade, Exam, Role, Submission
from app.result_release import synchronize_result_release

from . import student_bp


def _student_submission(submission_id: int) -> Submission:
    """Load one finalized submission belonging to the logged-in Student."""

    submission = db.session.scalar(
        select(Submission)
        .where(
            Submission.id == submission_id,
            Submission.candidate_email == current_user.email,
            Submission.submitted_at.is_not(None),
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


@student_bp.get("/")
@role_required(Role.STUDENT)
def index():
    """Show the Student's in-progress and completed examination attempts."""

    submissions = db.session.scalars(
        select(Submission)
        .where(Submission.candidate_email == current_user.email)
        .options(
            selectinload(Submission.exam).selectinload(Exam.questions),
            selectinload(Submission.answer_grades),
            selectinload(Submission.result),
        )
        .order_by(Submission.started_at.desc())
    ).all()
    for submission in submissions:
        if submission.is_finalized:
            result = grade_submission(submission)
            synchronize_result_release(result)
    db.session.commit()
    return render_template("student/dashboard.html", submissions=submissions)


@student_bp.get("/results/<int:submission_id>")
@role_required(Role.STUDENT)
def result(submission_id: int):
    """Show only this Student's released result or its pending state."""

    submission = _student_submission(submission_id)
    result = grade_submission(submission)
    synchronize_result_release(result)
    db.session.commit()

    if not result.is_released:
        return render_template(
            "candidate/result_pending.html",
            exam=submission.exam,
            submission=submission,
            result=result,
            awaiting_manual_review=(
                result.status.value == "pending_manual_review"
            ),
        )

    grades_by_question = {
        grade.question_id: grade for grade in submission.answer_grades
    }
    result_rows = [
        {
            "question": question,
            "response": (submission.responses or {}).get(str(question.id), ""),
            "grade": grades_by_question[question.id],
        }
        for question in submission.exam.questions
    ]
    return render_template(
        "candidate/result.html",
        exam=submission.exam,
        submission=submission,
        result=result,
        result_rows=result_rows,
    )

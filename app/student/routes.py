"""Student course, invitation, examination, and result routes."""

from datetime import UTC, datetime

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.access import role_required
from app.extensions import db
from app.grading import grade_submission
from app.models import (
    AnswerGrade,
    Course,
    CourseEnrollment,
    EnrollmentStatus,
    Exam,
    Role,
    Submission,
)
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
    """Show pending invitations and course-grouped Student resources."""

    enrollments = db.session.scalars(
        select(CourseEnrollment)
        .where(CourseEnrollment.student_id == current_user.id)
        .options(
            selectinload(CourseEnrollment.course).selectinload(Course.exams),
            selectinload(CourseEnrollment.invited_by),
        )
        .order_by(CourseEnrollment.created_at.desc())
    ).all()

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
    submissions_by_exam = {
        submission.exam_id: submission for submission in submissions
    }
    accepted_enrollments = [
        enrollment
        for enrollment in enrollments
        if enrollment.status is EnrollmentStatus.ACCEPTED
    ]
    pending_enrollments = [
        enrollment
        for enrollment in enrollments
        if enrollment.status is EnrollmentStatus.PENDING
    ]
    return render_template(
        "student/dashboard.html",
        accepted_enrollments=accepted_enrollments,
        pending_enrollments=pending_enrollments,
        submissions_by_exam=submissions_by_exam,
    )


@student_bp.post("/invitations/<int:enrollment_id>/accept")
@role_required(Role.STUDENT)
def accept_invitation(enrollment_id: int):
    """Accept one invitation addressed to the authenticated Student."""

    enrollment = db.session.scalar(
        select(CourseEnrollment).where(
            CourseEnrollment.id == enrollment_id,
            CourseEnrollment.student_id == current_user.id,
        )
    )
    if enrollment is None:
        abort(404)
    if enrollment.status is EnrollmentStatus.PENDING:
        enrollment.status = EnrollmentStatus.ACCEPTED
        enrollment.accepted_at = datetime.now(UTC)
        db.session.commit()
        flash(f"You are now enrolled in {enrollment.course.code}.", "success")
    else:
        flash("You have already accepted that course invitation.", "info")
    return redirect(url_for("student.index"))


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

"""Student course, invitation, examination, and result routes."""

from datetime import UTC, datetime

from flask import abort, flash, redirect, render_template, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.access import role_required
from app.candidate.services import aware_utc, utc_now
from app.candidate.session_services import exam_availability
from app.coursework_files import (
    CourseworkFileError,
    delete_coursework_file,
    save_coursework_file,
    storage_directory,
)
from app.extensions import db
from app.grading import grade_submission
from app.models import (
    AnswerGrade,
    Assignment,
    AssignmentSubmission,
    Course,
    CourseEnrollment,
    CourseMaterial,
    EnrollmentStatus,
    Exam,
    Role,
    Submission,
)
from app.result_release import synchronize_result_release

from . import student_bp
from .forms import AssignmentSubmissionForm


def _accepted_course(course_id: int) -> Course:
    course = db.session.scalar(
        select(Course)
        .join(CourseEnrollment)
        .where(
            Course.id == course_id,
            CourseEnrollment.student_id == current_user.id,
            CourseEnrollment.status == EnrollmentStatus.ACCEPTED,
        )
        .options(
            selectinload(Course.announcements),
            selectinload(Course.materials),
            selectinload(Course.assignments).selectinload(Assignment.submissions),
            selectinload(Course.exams),
        )
    )
    if course is None:
        abort(404)
    return course


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
            selectinload(Submission.answer_grades).selectinload(AnswerGrade.question),
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
    submissions_by_exam = {}
    for submission in submissions:
        submissions_by_exam.setdefault(submission.exam_id, submission)
    attempt_counts_by_exam: dict[int, int] = {}
    for submission in submissions:
        attempt_counts_by_exam[submission.exam_id] = (
            attempt_counts_by_exam.get(submission.exam_id, 0) + 1
        )
    exam_states = {
        exam.id: exam_availability(exam)
        for enrollment in enrollments
        for exam in enrollment.course.exams
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
        attempt_counts_by_exam=attempt_counts_by_exam,
        exam_states=exam_states,
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


@student_bp.get("/courses/<int:course_id>")
@role_required(Role.STUDENT)
def course_detail(course_id: int):
    """Show an enrolled Student's course announcements and learning resources."""

    course = _accepted_course(course_id)
    submissions = {
        submission.assignment_id: submission
        for assignment in course.assignments
        for submission in assignment.submissions
        if submission.student_id == current_user.id
    }
    return render_template(
        "student/course_detail.html", course=course, submissions=submissions
    )


@student_bp.get("/materials/<int:material_id>/download")
@role_required(Role.STUDENT)
def download_material(material_id: int):
    material = db.session.get(CourseMaterial, material_id)
    if material is None or not material.storage_name:
        abort(404)
    _accepted_course(material.course_id)
    return send_from_directory(
        storage_directory("course_materials"),
        material.storage_name,
        as_attachment=True,
        download_name=material.original_filename,
    )


@student_bp.route("/assignments/<int:assignment_id>", methods=["GET", "POST"])
@role_required(Role.STUDENT)
def assignment(assignment_id: int):
    """Display and accept one enrolled Student's assignment submission."""

    assignment = db.session.get(Assignment, assignment_id)
    if assignment is None or not assignment.is_published:
        abort(404)
    _accepted_course(assignment.course_id)
    submission = db.session.scalar(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment.id,
            AssignmentSubmission.student_id == current_user.id,
        )
    )
    form = AssignmentSubmissionForm()
    if form.validate_on_submit():
        if utc_now() > aware_utc(assignment.due_at):
            flash("The submission deadline has passed.", "error")
            return redirect(url_for("student.assignment", assignment_id=assignment.id))
        text_response = (form.text_response.data or "").strip()
        upload = form.submission_file.data
        if not text_response and not upload and not submission:
            flash("Add a written response or an attachment.", "error")
            return redirect(url_for("student.assignment", assignment_id=assignment.id))
        old_storage_name = submission.storage_name if submission else None
        storage_name = original_filename = None
        try:
            if upload:
                storage_name, original_filename = save_coursework_file(
                    upload, "assignment_submissions"
                )
        except CourseworkFileError as error:
            flash(str(error), "error")
            return redirect(url_for("student.assignment", assignment_id=assignment.id))
        if submission is None:
            submission = AssignmentSubmission(
                assignment=assignment, student=current_user, submitted_at=utc_now()
            )
            db.session.add(submission)
        submission.text_response = text_response or submission.text_response
        if storage_name:
            submission.storage_name = storage_name
            submission.original_filename = original_filename
        submission.submitted_at = utc_now()
        submission.awarded_marks = None
        submission.feedback = None
        submission.graded_at = None
        submission.graded_by_id = None
        db.session.commit()
        if storage_name:
            delete_coursework_file(old_storage_name, "assignment_submissions")
        flash("Assignment submitted successfully.", "success")
        return redirect(url_for("student.assignment", assignment_id=assignment.id))
    return render_template(
        "student/assignment.html",
        assignment=assignment,
        submission=submission,
        form=form,
        deadline_passed=utc_now() > aware_utc(assignment.due_at),
    )


@student_bp.get("/assignment-submissions/<int:submission_id>/download")
@role_required(Role.STUDENT)
def download_assignment_submission(submission_id: int):
    submission = db.session.scalar(
        select(AssignmentSubmission).where(
            AssignmentSubmission.id == submission_id,
            AssignmentSubmission.student_id == current_user.id,
        )
    )
    if submission is None or not submission.storage_name:
        abort(404)
    return send_from_directory(
        storage_directory("assignment_submissions"),
        submission.storage_name,
        as_attachment=True,
        download_name=submission.original_filename,
    )


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
            awaiting_manual_review=(result.status.value == "pending_manual_review"),
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

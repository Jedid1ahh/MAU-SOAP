"""Lecturer course dashboard and invitation routes."""

from __future__ import annotations

import re

from flask import abort, current_app, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Course, CourseEnrollment, EnrollmentStatus, Role, User

from . import lecturer_bp
from .auth import lecturer_required
from .forms import CourseInvitationForm


def owned_course(course_id: int) -> Course:
    """Load a complete course workspace assigned to the current Lecturer."""

    course = db.session.scalar(
        select(Course)
        .where(
            Course.id == course_id,
            Course.lecturer_id == current_user.id,
        )
        .options(
            selectinload(Course.exams),
            selectinload(Course.enrollments).selectinload(
                CourseEnrollment.student
            ),
        )
    )
    if course is None:
        abort(404)
    return course


def _normalized_emails(raw_value: str) -> list[str]:
    """Return unique, normalized addresses from common roster separators."""

    values = re.split(r"[\s,;]+", raw_value.strip())
    return list(dict.fromkeys(value.casefold() for value in values if value))


@lecturer_bp.get("/")
@lecturer_required
def index():
    """Show every course currently assigned to the Lecturer."""

    courses = db.session.scalars(
        select(Course)
        .where(Course.lecturer_id == current_user.id)
        .options(
            selectinload(Course.exams),
            selectinload(Course.enrollments),
        )
        .order_by(Course.code)
    ).all()
    return render_template("lecturer/dashboard.html", courses=courses)


@lecturer_bp.get("/courses/<int:course_id>")
@lecturer_required
def course_detail(course_id: int):
    """Show a course roster and its categorized examinations."""

    course = owned_course(course_id)
    return render_template(
        "lecturer/course_detail.html",
        course=course,
        accepted_enrollments=[
            enrollment
            for enrollment in course.enrollments
            if enrollment.status is EnrollmentStatus.ACCEPTED
        ],
        pending_enrollments=[
            enrollment
            for enrollment in course.enrollments
            if enrollment.status is EnrollmentStatus.PENDING
        ],
        invitation_form=CourseInvitationForm(),
    )


@lecturer_bp.post("/courses/<int:course_id>/invitations")
@lecturer_required
def invite_students(course_id: int):
    """Invite registered Student accounts into one owned course."""

    course = owned_course(course_id)
    form = CourseInvitationForm()
    if not form.validate_on_submit():
        flash("Enter at least one registered Student email address.", "error")
        return redirect(url_for("lecturer.course_detail", course_id=course.id))

    emails = _normalized_emails(form.student_emails.data)
    student_domain = str(
        current_app.config["CANDIDATE_EMAIL_DOMAIN"]
    ).casefold()
    valid_domain_emails = [
        email
        for email in emails
        if email.rsplit("@", 1)[-1] == student_domain
    ]
    invalid_emails = sorted(set(emails) - set(valid_domain_emails))

    students = db.session.scalars(
        select(User).where(
            User.email.in_(valid_domain_emails),
            User.role == Role.STUDENT,
            User.is_active.is_(True),
        )
    ).all()
    students_by_email = {student.email: student for student in students}
    missing_emails = sorted(set(valid_domain_emails) - set(students_by_email))

    existing = {
        enrollment.student_id: enrollment for enrollment in course.enrollments
    }
    invited_count = 0
    for student in students:
        enrollment = existing.get(student.id)
        if enrollment is None:
            db.session.add(
                CourseEnrollment(
                    course=course,
                    student=student,
                    invited_by=current_user,
                    status=EnrollmentStatus.PENDING,
                )
            )
            invited_count += 1
        elif enrollment.status is EnrollmentStatus.PENDING:
            enrollment.invited_by = current_user

    db.session.commit()
    if invited_count:
        flash(f"Sent {invited_count} course invitation(s).", "success")
    if invalid_emails:
        flash(
            "Ignored non-student-domain address(es): " + ", ".join(invalid_emails),
            "error",
        )
    if missing_emails:
        flash(
            "No registered Student account was found for: "
            + ", ".join(missing_emails),
            "error",
        )
    if not invited_count and not invalid_emails and not missing_emails:
        flash("Those Students are already invited or enrolled.", "info")
    return redirect(url_for("lecturer.course_detail", course_id=course.id))

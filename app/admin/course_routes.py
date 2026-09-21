"""Admin course creation and Lecturer-assignment routes."""

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Course, Role, User

from . import admin_bp
from .auth import admin_required
from .course_forms import CourseForm


def _available_lecturers() -> list[User]:
    """Return active, verified, approved Lecturers for course assignment."""

    return db.session.scalars(
        select(User)
        .where(
            User.role == Role.LECTURER,
            User.is_active.is_(True),
            User.email_verified_at.is_not(None),
            User.approved_at.is_not(None),
        )
        .order_by(User.full_name, User.email)
    ).all()


def _course(course_id: int) -> Course:
    course = db.session.scalar(
        select(Course)
        .where(Course.id == course_id)
        .options(
            selectinload(Course.lecturer),
            selectinload(Course.exams),
            selectinload(Course.enrollments),
        )
    )
    if course is None:
        abort(404)
    return course


def _course_form(course: Course | None = None) -> CourseForm:
    """Build the form with only assignable Lecturer accounts."""

    if request.method == "POST":
        form = CourseForm()
    else:
        form = CourseForm(
            data=(
                {
                    "code": course.code,
                    "title": course.title,
                    "description": course.description,
                    "lecturer_id": course.lecturer_id,
                }
                if course is not None
                else None
            )
        )
    lecturers = _available_lecturers()
    form.lecturer_id.choices = [
        (lecturer.id, f"{lecturer.full_name} — {lecturer.email}")
        for lecturer in lecturers
    ]
    return form


def _apply_form(course: Course, form: CourseForm) -> None:
    """Apply validated values and transfer every exam with reassignment."""

    new_lecturer_id = form.lecturer_id.data
    course.code = form.code.data.strip().upper()
    course.title = form.title.data.strip()
    course.description = (form.description.data or "").strip() or None
    lecturer_changed = course.lecturer_id != new_lecturer_id
    course.lecturer_id = new_lecturer_id
    for exam in course.exams:
        exam.course_code = course.code
        exam.course_title = course.title
        if lecturer_changed:
            exam.admin_id = new_lecturer_id


@admin_bp.route("/courses/new", methods=["GET", "POST"])
@admin_required
def create_course():
    """Create one course and assign its sole current Lecturer."""

    form = _course_form()
    if form.validate_on_submit():
        code = form.code.data.strip().upper()
        existing = db.session.scalar(select(Course).where(Course.code == code))
        if existing is not None:
            form.code.errors.append("A course with this code already exists.")
        else:
            course = Course(
                code=code,
                title=form.title.data.strip(),
                description=(form.description.data or "").strip() or None,
                lecturer_id=form.lecturer_id.data,
                created_by_admin_id=current_user.id,
            )
            db.session.add(course)
            db.session.commit()
            flash("Course created and assigned to the Lecturer.", "success")
            return redirect(url_for("admin.index"))

    return render_template(
        "admin/course_form.html",
        form=form,
        form_title="Create course",
        submit_label="Create course",
    )


@admin_bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_course(course_id: int):
    """Edit or transfer an entire course workspace to another Lecturer."""

    course = _course(course_id)
    form = _course_form(course)
    if form.validate_on_submit():
        code = form.code.data.strip().upper()
        duplicate = db.session.scalar(
            select(Course).where(
                Course.code == code,
                Course.id != course.id,
            )
        )
        if duplicate is not None:
            form.code.errors.append("A course with this code already exists.")
        else:
            _apply_form(course, form)
            db.session.commit()
            flash("Course assignment and details updated.", "success")
            return redirect(url_for("admin.index"))

    return render_template(
        "admin/course_form.html",
        form=form,
        course=course,
        form_title="Edit course",
        submit_label="Save course",
    )

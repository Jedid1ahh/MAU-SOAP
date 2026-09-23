"""Lecturer announcements, materials, assignments, and grading routes."""

from datetime import UTC, datetime

from flask import abort, flash, redirect, render_template, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.coursework_files import (
    CourseworkFileError,
    delete_coursework_file,
    save_coursework_file,
    storage_directory,
)
from app.extensions import db
from app.models import (
    Assignment,
    AssignmentSubmission,
    Course,
    CourseAnnouncement,
    CourseMaterial,
)

from . import lecturer_bp
from .auth import lecturer_required
from .forms import (
    AnnouncementForm,
    AssignmentForm,
    AssignmentGradeForm,
    MaterialForm,
)
from .routes import owned_course


def _owned_assignment(assignment_id: int) -> Assignment:
    assignment = db.session.scalar(
        select(Assignment)
        .join(Course)
        .where(
            Assignment.id == assignment_id,
            Course.lecturer_id == current_user.id,
        )
        .options(
            selectinload(Assignment.submissions).selectinload(
                AssignmentSubmission.student
            )
        )
    )
    if assignment is None:
        abort(404)
    return assignment


@lecturer_bp.post("/courses/<int:course_id>/announcements")
@lecturer_required
def create_announcement(course_id: int):
    course = owned_course(course_id)
    form = AnnouncementForm()
    if form.validate_on_submit():
        db.session.add(
            CourseAnnouncement(
                course=course,
                author=current_user,
                title=form.title.data.strip(),
                body=form.body.data.strip(),
                is_pinned=form.is_pinned.data,
            )
        )
        db.session.commit()
        flash("Announcement published.", "success")
    else:
        flash("Complete the announcement title and message.", "error")
    return redirect(url_for("lecturer.course_detail", course_id=course.id))


@lecturer_bp.post("/courses/<int:course_id>/materials")
@lecturer_required
def create_material(course_id: int):
    course = owned_course(course_id)
    form = MaterialForm()
    upload = form.material_file.data
    if not form.validate_on_submit() or (not form.external_url.data and not upload):
        flash("Add a valid link or supported file for this material.", "error")
        return redirect(url_for("lecturer.course_detail", course_id=course.id))
    storage_name = original_filename = None
    try:
        if upload:
            storage_name, original_filename = save_coursework_file(
                upload, "course_materials"
            )
    except CourseworkFileError as error:
        flash(str(error), "error")
        return redirect(url_for("lecturer.course_detail", course_id=course.id))
    db.session.add(
        CourseMaterial(
            course=course,
            uploaded_by=current_user,
            title=form.title.data.strip(),
            description=(form.description.data or "").strip() or None,
            external_url=form.external_url.data or None,
            storage_name=storage_name,
            original_filename=original_filename,
        )
    )
    db.session.commit()
    flash("Course material added.", "success")
    return redirect(url_for("lecturer.course_detail", course_id=course.id))


@lecturer_bp.get("/materials/<int:material_id>/download")
@lecturer_required
def download_material(material_id: int):
    material = db.session.scalar(
        select(CourseMaterial)
        .join(Course)
        .where(
            CourseMaterial.id == material_id,
            Course.lecturer_id == current_user.id,
        )
    )
    if material is None or not material.storage_name:
        abort(404)
    return send_from_directory(
        storage_directory("course_materials"),
        material.storage_name,
        as_attachment=True,
        download_name=material.original_filename,
    )


@lecturer_bp.route("/courses/<int:course_id>/assignments/new", methods=["GET", "POST"])
@lecturer_required
def create_assignment(course_id: int):
    course = owned_course(course_id)
    form = AssignmentForm()
    if form.validate_on_submit():
        assignment = Assignment(
            course=course,
            created_by=current_user,
            title=form.title.data.strip(),
            instructions=form.instructions.data.strip(),
            due_at=form.due_at.data.replace(tzinfo=UTC),
            max_marks=form.max_marks.data,
            is_published=form.is_published.data,
        )
        db.session.add(assignment)
        db.session.commit()
        flash("Assignment created.", "success")
        return redirect(
            url_for("lecturer.assignment_detail", assignment_id=assignment.id)
        )
    return render_template("lecturer/assignment_form.html", course=course, form=form)


@lecturer_bp.get("/assignments/<int:assignment_id>")
@lecturer_required
def assignment_detail(assignment_id: int):
    return render_template(
        "lecturer/assignment_detail.html",
        assignment=_owned_assignment(assignment_id),
        grade_form=AssignmentGradeForm(),
    )


@lecturer_bp.post(
    "/assignments/<int:assignment_id>/submissions/<int:submission_id>/grade"
)
@lecturer_required
def grade_assignment_submission(assignment_id: int, submission_id: int):
    assignment = _owned_assignment(assignment_id)
    submission = next(
        (item for item in assignment.submissions if item.id == submission_id), None
    )
    if submission is None:
        abort(404)
    form = AssignmentGradeForm()
    if form.validate_on_submit() and form.awarded_marks.data <= assignment.max_marks:
        submission.awarded_marks = form.awarded_marks.data
        submission.feedback = (form.feedback.data or "").strip() or None
        submission.graded_at = datetime.now(UTC)
        submission.graded_by = current_user
        db.session.commit()
        flash("Assignment grade saved.", "success")
    else:
        flash(f"Enter a grade between 0 and {assignment.max_marks}.", "error")
    return redirect(url_for("lecturer.assignment_detail", assignment_id=assignment.id))


@lecturer_bp.get("/assignment-submissions/<int:submission_id>/download")
@lecturer_required
def download_assignment_submission(submission_id: int):
    submission = db.session.scalar(
        select(AssignmentSubmission)
        .join(Assignment)
        .join(Course)
        .where(
            AssignmentSubmission.id == submission_id,
            Course.lecturer_id == current_user.id,
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


@lecturer_bp.post("/courses/<int:course_id>/materials/<int:material_id>/delete")
@lecturer_required
def delete_material(course_id: int, material_id: int):
    course = owned_course(course_id)
    material = db.session.scalar(
        select(CourseMaterial).where(
            CourseMaterial.id == material_id,
            CourseMaterial.course_id == course.id,
        )
    )
    if material is None:
        abort(404)
    storage_name = material.storage_name
    db.session.delete(material)
    db.session.commit()
    delete_coursework_file(storage_name, "course_materials")
    flash("Course material removed.", "success")
    return redirect(url_for("lecturer.course_detail", course_id=course.id))

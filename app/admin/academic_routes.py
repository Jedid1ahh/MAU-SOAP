"""Admin routes for academic sessions and organizational structure."""

from flask import flash, redirect, render_template, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import AcademicSession, Department, Faculty, Programme, Semester

from . import admin_bp
from .academic_forms import (
    AcademicSessionForm,
    DepartmentForm,
    FacultyForm,
    ProgrammeForm,
    SemesterForm,
)
from .auth import admin_required


def _form_choices(forms: tuple) -> None:
    sessions = db.session.scalars(
        select(AcademicSession).order_by(AcademicSession.start_date.desc())
    ).all()
    faculties = db.session.scalars(select(Faculty).order_by(Faculty.name)).all()
    departments = db.session.scalars(select(Department).order_by(Department.name)).all()
    for form in forms:
        if hasattr(form, "academic_session_id"):
            form.academic_session_id.choices = [
                (item.id, item.name) for item in sessions
            ]
        if hasattr(form, "faculty_id"):
            form.faculty_id.choices = [
                (item.id, f"{item.code} — {item.name}") for item in faculties
            ]
        if hasattr(form, "department_id"):
            form.department_id.choices = [
                (item.id, f"{item.code} — {item.name}") for item in departments
            ]


def _commit_structure(success_message: str) -> bool:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("That academic-structure code or name already exists.", "error")
        return False
    flash(success_message, "success")
    return True


@admin_bp.get("/academic-structure")
@admin_required
def academic_structure():
    """Show the session, faculty, department, and programme registry."""

    session_form = AcademicSessionForm(prefix="session")
    semester_form = SemesterForm(prefix="semester")
    faculty_form = FacultyForm(prefix="faculty")
    department_form = DepartmentForm(prefix="department")
    programme_form = ProgrammeForm(prefix="programme")
    _form_choices(
        (
            session_form,
            semester_form,
            faculty_form,
            department_form,
            programme_form,
        )
    )
    sessions = db.session.scalars(
        select(AcademicSession)
        .options(selectinload(AcademicSession.semesters))
        .order_by(AcademicSession.start_date.desc())
    ).all()
    faculties = db.session.scalars(
        select(Faculty)
        .options(selectinload(Faculty.departments).selectinload(Department.programmes))
        .order_by(Faculty.name)
    ).all()
    return render_template(
        "admin/academic_structure.html",
        sessions=sessions,
        faculties=faculties,
        session_form=session_form,
        semester_form=semester_form,
        faculty_form=faculty_form,
        department_form=department_form,
        programme_form=programme_form,
    )


@admin_bp.post("/academic-structure/sessions")
@admin_required
def create_academic_session():
    form = AcademicSessionForm(prefix="session")
    if form.validate_on_submit() and form.end_date.data > form.start_date.data:
        if form.is_current.data:
            db.session.query(AcademicSession).update({"is_current": False})
        db.session.add(
            AcademicSession(
                name=form.name.data.strip(),
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                is_current=form.is_current.data,
            )
        )
        _commit_structure("Academic session added.")
    else:
        flash("Enter a valid session with an end date after its start date.", "error")
    return redirect(url_for("admin.academic_structure"))


@admin_bp.post("/academic-structure/semesters")
@admin_required
def create_semester():
    form = SemesterForm(prefix="semester")
    _form_choices((form,))
    if form.validate_on_submit() and form.end_date.data > form.start_date.data:
        if form.is_current.data:
            db.session.query(Semester).update({"is_current": False})
        db.session.add(
            Semester(
                academic_session_id=form.academic_session_id.data,
                name=form.name.data.strip(),
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                is_current=form.is_current.data,
            )
        )
        _commit_structure("Semester added.")
    else:
        flash("Enter a valid semester with an end date after its start date.", "error")
    return redirect(url_for("admin.academic_structure"))


@admin_bp.post("/academic-structure/faculties")
@admin_required
def create_faculty():
    form = FacultyForm(prefix="faculty")
    if form.validate_on_submit():
        db.session.add(
            Faculty(code=form.code.data.strip().upper(), name=form.name.data.strip())
        )
        _commit_structure("Faculty added.")
    else:
        flash("Enter a valid faculty code and name.", "error")
    return redirect(url_for("admin.academic_structure"))


@admin_bp.post("/academic-structure/departments")
@admin_required
def create_department():
    form = DepartmentForm(prefix="department")
    _form_choices((form,))
    if form.validate_on_submit():
        db.session.add(
            Department(
                faculty_id=form.faculty_id.data,
                code=form.code.data.strip().upper(),
                name=form.name.data.strip(),
            )
        )
        _commit_structure("Department added.")
    else:
        flash("Enter a valid department and select its faculty.", "error")
    return redirect(url_for("admin.academic_structure"))


@admin_bp.post("/academic-structure/programmes")
@admin_required
def create_programme():
    form = ProgrammeForm(prefix="programme")
    _form_choices((form,))
    if form.validate_on_submit():
        db.session.add(
            Programme(
                department_id=form.department_id.data,
                code=form.code.data.strip().upper(),
                name=form.name.data.strip(),
                award=(form.award.data or "").strip() or None,
            )
        )
        _commit_structure("Programme added.")
    else:
        flash("Enter a valid programme and select its department.", "error")
    return redirect(url_for("admin.academic_structure"))

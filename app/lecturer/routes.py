"""Lecturer dashboard routes."""

from flask import render_template
from flask_login import current_user
from sqlalchemy import select

from app.access import role_required
from app.extensions import db
from app.models import Exam, Role

from . import lecturer_bp


@lecturer_bp.get("/")
@role_required(Role.LECTURER)
def index():
    """Show examinations owned by the approved Lecturer."""

    exams = db.session.scalars(
        select(Exam)
        .where(Exam.admin_id == current_user.id)
        .order_by(Exam.created_at.desc())
    ).all()
    return render_template("lecturer/dashboard.html", exams=exams)

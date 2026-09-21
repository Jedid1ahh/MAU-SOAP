"""Shared factories for course-centered test data."""

from sqlalchemy import select

from app.extensions import db
from app.models import Course, Role, User


def course_for(owner: User, code: str, title: str) -> Course:
    """Return a persisted course suitable for an Exam owned by ``owner``."""

    normalized_code = code.strip().upper()
    course = next(
        (
            item
            for item in db.session.new
            if isinstance(item, Course) and item.code == normalized_code
        ),
        None,
    )
    if course is None:
        course = db.session.scalar(
            select(Course).where(Course.code == normalized_code)
        )
    if course is not None:
        return course

    creator = owner
    if owner.role is not Role.ADMIN:
        creator = db.session.scalar(
            select(User).where(User.role == Role.ADMIN)
        ) or owner
    course = Course(
        code=normalized_code,
        title=title,
        lecturer=owner if owner.role is Role.LECTURER else None,
        created_by=creator,
    )
    db.session.add(course)
    db.session.flush()
    return course

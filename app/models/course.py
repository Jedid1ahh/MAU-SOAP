"""Course workspace model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin

if TYPE_CHECKING:
    from .course_enrollment import CourseEnrollment
    from .exam import Exam
    from .user import User


class Course(TimestampMixin, db.Model):
    """An Admin-created course assigned to at most one Lecturer."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    lecturer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    created_by_admin_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )

    lecturer: Mapped[User | None] = relationship(
        back_populates="assigned_courses",
        foreign_keys=[lecturer_id],
    )
    created_by: Mapped[User] = relationship(
        back_populates="created_courses",
        foreign_keys=[created_by_admin_id],
    )
    exams: Mapped[list[Exam]] = relationship(
        back_populates="course",
        order_by="Exam.created_at",
    )
    enrollments: Mapped[list[CourseEnrollment]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CourseEnrollment.created_at",
    )

    def __repr__(self) -> str:
        return f"<Course id={self.id!r} code={self.code!r}>"

"""Course workspace model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin

if TYPE_CHECKING:
    from .academic import Department, Programme, Semester
    from .course_enrollment import CourseEnrollment
    from .coursework import Assignment, CourseAnnouncement, CourseMaterial
    from .exam import Exam
    from .question_bank_item import QuestionBankItem
    from .user import User


class Course(TimestampMixin, db.Model):
    """An Admin-created course assigned to at most one Lecturer."""

    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("level IS NULL OR level > 0", name="positive_course_level"),
        CheckConstraint(
            "credit_units IS NULL OR credit_units > 0",
            name="positive_credit_units",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    semester_id: Mapped[int | None] = mapped_column(
        ForeignKey("semesters.id", ondelete="SET NULL"), index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    programme_id: Mapped[int | None] = mapped_column(
        ForeignKey("programmes.id", ondelete="SET NULL"), index=True
    )
    level: Mapped[int | None]
    credit_units: Mapped[int | None]
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
    semester: Mapped[Semester | None] = relationship(back_populates="courses")
    department: Mapped[Department | None] = relationship(back_populates="courses")
    programme: Mapped[Programme | None] = relationship(back_populates="courses")
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
    question_bank_items: Mapped[list[QuestionBankItem]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionBankItem.category, QuestionBankItem.created_at",
    )
    announcements: Mapped[list[CourseAnnouncement]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=(
            "CourseAnnouncement.is_pinned.desc(), CourseAnnouncement.created_at.desc()"
        ),
    )
    materials: Mapped[list[CourseMaterial]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CourseMaterial.created_at.desc()",
    )
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Assignment.due_at",
    )

    def __repr__(self) -> str:
        return f"<Course id={self.id!r} code={self.code!r}>"

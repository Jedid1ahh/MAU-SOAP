"""Student course invitation and enrollment model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin, database_enum
from .enums import EnrollmentStatus

if TYPE_CHECKING:
    from .course import Course
    from .user import User


class CourseEnrollment(TimestampMixin, db.Model):
    """A registered Student's pending or accepted course membership."""

    __tablename__ = "course_enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", name="course_student"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    invited_by_lecturer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        database_enum(EnrollmentStatus, "enrollment_status"),
        default=EnrollmentStatus.PENDING,
        server_default=EnrollmentStatus.PENDING.value,
        index=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course: Mapped[Course] = relationship(back_populates="enrollments")
    student: Mapped[User] = relationship(
        back_populates="course_enrollments",
        foreign_keys=[student_id],
    )
    invited_by: Mapped[User | None] = relationship(
        back_populates="sent_course_invitations",
        foreign_keys=[invited_by_lecturer_id],
    )

    @property
    def is_accepted(self) -> bool:
        return self.status is EnrollmentStatus.ACCEPTED

    def __repr__(self) -> str:
        return (
            f"<CourseEnrollment id={self.id!r} "
            f"course_id={self.course_id!r} student_id={self.student_id!r}>"
        )

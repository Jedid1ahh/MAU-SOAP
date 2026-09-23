"""Per-Student examination accommodation model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin

if TYPE_CHECKING:
    from .exam import Exam
    from .user import User


class ExamAccommodation(TimestampMixin, db.Model):
    """Additional time granted to one enrolled Student for one exam."""

    __tablename__ = "exam_accommodations"
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", name="exam_student_accommodation"),
        CheckConstraint("extra_time_minutes >= 0", name="nonnegative_extra_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    extra_time_minutes: Mapped[int] = mapped_column(default=0, server_default="0")

    exam: Mapped[Exam] = relationship(back_populates="accommodations")
    student: Mapped[User] = relationship(back_populates="exam_accommodations")

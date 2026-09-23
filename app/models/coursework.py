"""Course announcements, materials, assignments, and submissions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin

if TYPE_CHECKING:
    from .course import Course
    from .user import User


class CourseAnnouncement(TimestampMixin, db.Model):
    """A Lecturer-authored announcement visible to enrolled Students."""

    __tablename__ = "course_announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )

    course: Mapped[Course] = relationship(back_populates="announcements")
    author: Mapped[User] = relationship(back_populates="course_announcements")


class CourseMaterial(TimestampMixin, db.Model):
    """A course resource supplied as an external link or uploaded file."""

    __tablename__ = "course_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    external_url: Mapped[str | None] = mapped_column(String(2048))
    storage_name: Mapped[str | None] = mapped_column(String(255), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))

    course: Mapped[Course] = relationship(back_populates="materials")
    uploaded_by: Mapped[User] = relationship(back_populates="course_materials")


class Assignment(TimestampMixin, db.Model):
    """A published course task with one deadline and mark value."""

    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    instructions: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    max_marks: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    is_published: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), index=True
    )

    course: Mapped[Course] = relationship(back_populates="assignments")
    created_by: Mapped[User] = relationship(back_populates="created_assignments")
    submissions: Mapped[list[AssignmentSubmission]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssignmentSubmission.submitted_at",
    )


class AssignmentSubmission(TimestampMixin, db.Model):
    """One Student's replaceable submission for one assignment."""

    __tablename__ = "assignment_submissions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="assignment_student"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    text_response: Mapped[str | None] = mapped_column(Text)
    storage_name: Mapped[str | None] = mapped_column(String(255), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    awarded_marks: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    feedback: Mapped[str | None] = mapped_column(Text)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    graded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")
    student: Mapped[User] = relationship(
        back_populates="assignment_submissions", foreign_keys=[student_id]
    )
    graded_by: Mapped[User | None] = relationship(
        back_populates="graded_assignment_submissions", foreign_keys=[graded_by_id]
    )

"""Academic-session and organizational structure models."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin

if TYPE_CHECKING:
    from .course import Course


class AcademicSession(TimestampMixin, db.Model):
    """One university academic year, such as 2026/2027."""

    __tablename__ = "academic_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), index=True
    )

    semesters: Mapped[list[Semester]] = relationship(
        back_populates="academic_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Semester.start_date",
    )


class Semester(TimestampMixin, db.Model):
    """A bounded teaching period within one academic session."""

    __tablename__ = "semesters"
    __table_args__ = (
        UniqueConstraint("academic_session_id", "name", name="session_semester"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_session_id: Mapped[int] = mapped_column(
        ForeignKey("academic_sessions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), index=True
    )

    academic_session: Mapped[AcademicSession] = relationship(back_populates="semesters")
    courses: Mapped[list[Course]] = relationship(back_populates="semester")


class Faculty(TimestampMixin, db.Model):
    """Top-level academic organization."""

    __tablename__ = "faculties"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)

    departments: Mapped[list[Department]] = relationship(
        back_populates="faculty",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Department.name",
    )


class Department(TimestampMixin, db.Model):
    """Department within one faculty."""

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculties.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)

    faculty: Mapped[Faculty] = relationship(back_populates="departments")
    programmes: Mapped[list[Programme]] = relationship(
        back_populates="department",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Programme.name",
    )
    courses: Mapped[list[Course]] = relationship(back_populates="department")


class Programme(TimestampMixin, db.Model):
    """Degree programme owned by an academic department."""

    __tablename__ = "programmes"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    award: Mapped[str | None] = mapped_column(String(100))

    department: Mapped[Department] = relationship(back_populates="programmes")
    courses: Mapped[list[Course]] = relationship(back_populates="programme")

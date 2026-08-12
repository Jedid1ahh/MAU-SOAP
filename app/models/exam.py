"""Examination configuration model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin, database_enum
from .enums import MonitorType, ReleaseOption

if TYPE_CHECKING:
    from .question import Question
    from .submission import Submission
    from .user import User
    from .verification_token import VerificationToken


class Exam(TimestampMixin, db.Model):
    """An Admin-owned exam and its supervision/release settings."""

    __tablename__ = "exams"
    __table_args__ = (
        CheckConstraint(
            "time_limit_minutes > 0",
            name="positive_time_limit",
        ),
        CheckConstraint(
            "release_option <> 'scheduled' OR scheduled_release_at IS NOT NULL",
            name="scheduled_release_has_time",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    course_code: Mapped[str] = mapped_column(String(50), index=True)
    course_title: Mapped[str] = mapped_column(String(255))
    instructions: Mapped[str | None] = mapped_column(Text)
    time_limit_minutes: Mapped[int]
    monitor_type: Mapped[MonitorType] = mapped_column(
        database_enum(MonitorType, "monitor_type")
    )
    release_option: Mapped[ReleaseOption] = mapped_column(
        database_enum(ReleaseOption, "release_option"),
        default=ReleaseOption.IMMEDIATE,
        server_default=ReleaseOption.IMMEDIATE.value,
    )
    scheduled_release_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    exam_link_token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    admin: Mapped[User] = relationship(back_populates="exams")
    questions: Mapped[list[Question]] = relationship(
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Question.position",
    )
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    verification_tokens: Mapped[list[VerificationToken]] = relationship(
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def is_locked(self) -> bool:
        """Return True once any Candidate has started this examination."""

        return any(submission.started_at is not None for submission in self.submissions)

    def __repr__(self) -> str:
        return f"<Exam id={self.id!r} title={self.title!r}>"
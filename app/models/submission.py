"""Candidate exam-session and submission model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import JSON_DOCUMENT, JsonObject, TimestampMixin

if TYPE_CHECKING:
    from .answer_grade import AnswerGrade
    from .exam import Exam
    from .result import Result
    from .warning_log import WarningLog


class Submission(TimestampMixin, db.Model):
    """A Candidate's single, resumable session for one examination."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("exam_id", "candidate_email", name="candidate_exam"),
        CheckConstraint("warn_count >= 0 AND warn_count <= 3", name="warning_range"),
        CheckConstraint(
            "submitted_at IS NULL OR submitted_at >= started_at",
            name="submission_after_start",
        ),
        Index("ix_submissions_candidate_email", "candidate_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"),
        index=True,
    )
    candidate_name: Mapped[str] = mapped_column(String(255))
    candidate_email: Mapped[str] = mapped_column(String(255))
    responses: Mapped[JsonObject] = mapped_column(
        MutableDict.as_mutable(JSON_DOCUMENT),
        default=dict,
    )
    resume_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    submission_reason: Mapped[str | None] = mapped_column(String(50))
    warn_count: Mapped[int] = mapped_column(default=0, server_default="0")

    supervision_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    exam: Mapped[Exam] = relationship(back_populates="submissions")
    result: Mapped[Result | None] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    warning_logs: Mapped[list[WarningLog]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WarningLog.occurred_at",
    )
    answer_grades: Mapped[list[AnswerGrade]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def is_finalized(self) -> bool:
        return self.submitted_at is not None

    def __repr__(self) -> str:
        return (
            f"<Submission id={self.id!r} exam_id={self.exam_id!r} "
            f"candidate_email={self.candidate_email!r}>"
        )
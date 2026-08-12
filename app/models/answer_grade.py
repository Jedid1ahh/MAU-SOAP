"""Per-question grading model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin, database_enum
from .enums import GradedBy

if TYPE_CHECKING:
    from .question import Question
    from .submission import Submission
    from .user import User


class AnswerGrade(TimestampMixin, db.Model):
    """Marks awarded to one response within one submission."""

    __tablename__ = "answer_grades"
    __table_args__ = (
        UniqueConstraint("submission_id", "question_id", name="submission_question"),
        CheckConstraint(
            "awarded_marks IS NULL OR awarded_marks >= 0",
            name="nonnegative_awarded_marks",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        index=True,
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        index=True,
    )
    awarded_marks: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    graded_by: Mapped[GradedBy | None] = mapped_column(
        database_enum(GradedBy, "graded_by")
    )
    grader_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    feedback: Mapped[str | None] = mapped_column(Text)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Submission] = relationship(back_populates="answer_grades")
    question: Mapped[Question] = relationship(back_populates="answer_grades")
    grader: Mapped[User | None] = relationship(
        back_populates="manual_grades",
        foreign_keys=[grader_user_id],
    )

    def __repr__(self) -> str:
        return (
            f"<AnswerGrade id={self.id!r} submission_id={self.submission_id!r} "
            f"question_id={self.question_id!r}>"
        )
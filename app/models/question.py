"""Exam question model."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import JSON_DOCUMENT, JsonObject, TimestampMixin, database_enum
from .enums import QuestionType

if TYPE_CHECKING:
    from .answer_grade import AnswerGrade
    from .exam import Exam


class Question(TimestampMixin, db.Model):
    """A positioned MCQ, short-answer, or open-ended exam question."""

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("exam_id", "position", name="question_position"),
        CheckConstraint("position > 0", name="positive_position"),
        CheckConstraint("marks > 0", name="positive_marks"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"),
        index=True,
    )
    question_text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[QuestionType] = mapped_column(
        database_enum(QuestionType, "question_type")
    )
    position: Mapped[int]
    marks: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    options: Mapped[JsonObject | None] = mapped_column(
        MutableDict.as_mutable(JSON_DOCUMENT)
    )
    correct_answer: Mapped[str | None] = mapped_column(Text)
    short_answer_case_sensitive: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
    )
    short_answer_trim_whitespace: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
    )

    exam: Mapped[Exam] = relationship(back_populates="questions")
    answer_grades: Mapped[list[AnswerGrade]] = relationship(
        back_populates="question",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Question id={self.id!r} exam_id={self.exam_id!r} "
            f"position={self.position!r}>"
        )
"""Reusable course question-bank model."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text, false, true
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import JSON_DOCUMENT, JsonObject, TimestampMixin, database_enum
from .enums import DifficultyLevel, QuestionType

if TYPE_CHECKING:
    from .course import Course
    from .question import Question
    from .user import User


class QuestionBankItem(TimestampMixin, db.Model):
    """A reusable question owned by one course and its Lecturer."""

    __tablename__ = "question_bank_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    lecturer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(100), index=True)
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        database_enum(DifficultyLevel, "difficulty_level"), index=True
    )
    question_text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[QuestionType] = mapped_column(
        database_enum(QuestionType, "bank_question_type")
    )
    marks: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    options: Mapped[JsonObject | None] = mapped_column(
        MutableDict.as_mutable(JSON_DOCUMENT)
    )
    correct_answer: Mapped[str | None] = mapped_column(Text)
    short_answer_case_sensitive: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    short_answer_trim_whitespace: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )

    course: Mapped[Course] = relationship(back_populates="question_bank_items")
    lecturer: Mapped[User] = relationship(back_populates="question_bank_items")
    exam_questions: Mapped[list[Question]] = relationship(
        back_populates="source_bank_item"
    )

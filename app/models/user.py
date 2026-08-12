"""Administrator account model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin, database_enum
from .enums import Role

if TYPE_CHECKING:
    from .answer_grade import AnswerGrade
    from .exam import Exam
    from .password_reset_token import PasswordResetToken


class User(TimestampMixin, db.Model):
    """The single pre-provisioned MAU-SOAP administrator."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        database_enum(Role, "role"),
        default=Role.ADMIN,
        server_default=Role.ADMIN.value,
        unique=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
    )

    exams: Mapped[list[Exam]] = relationship(
        back_populates="admin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    manual_grades: Mapped[list[AnswerGrade]] = relationship(
        back_populates="grader",
        foreign_keys="AnswerGrade.grader_user_id",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} email={self.email!r}>"
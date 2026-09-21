"""Authenticated MAU-SOAP account model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin, database_enum
from .enums import Role

if TYPE_CHECKING:
    from .account_verification_token import AccountVerificationToken
    from .answer_grade import AnswerGrade
    from .exam import Exam
    from .password_reset_token import PasswordResetToken


class User(UserMixin, TimestampMixin, db.Model):
    """An Admin, Lecturer, or Student account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        database_enum(Role, "role"),
        default=Role.ADMIN,
        server_default=Role.ADMIN.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    account_verification_tokens: Mapped[list[AccountVerificationToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    manual_grades: Mapped[list[AnswerGrade]] = relationship(
        back_populates="grader",
        foreign_keys="AnswerGrade.grader_user_id",
    )

    @property
    def is_email_verified(self) -> bool:
        """Return whether the institutional email address was verified."""

        return self.role is Role.ADMIN or self.email_verified_at is not None

    @property
    def is_approved(self) -> bool:
        """Return whether the account may pass its approval gate."""

        return self.role is not Role.LECTURER or self.approved_at is not None

    @property
    def can_access_portal(self) -> bool:
        """Return whether every login prerequisite is satisfied."""

        return self.is_active and self.is_email_verified and self.is_approved

    def __repr__(self) -> str:
        return f"<User id={self.id!r} email={self.email!r}>"

"""Candidate OTP and magic-link verification model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from .exam import Exam


class VerificationToken(db.Model):
    """Hashed, expiring credentials for passwordless Candidate verification."""

    __tablename__ = "verification_tokens"
    __table_args__ = (
        CheckConstraint("attempts >= 0 AND attempts <= 5", name="attempt_range"),
        Index(
            "ix_verification_tokens_exam_email",
            "exam_id",
            "candidate_email",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"))
    candidate_name: Mapped[str] = mapped_column(String(255))
    candidate_email: Mapped[str] = mapped_column(String(255), index=True)
    otp_hash: Mapped[str] = mapped_column(String(64), index=True)
    magic_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    exam: Mapped[Exam] = relationship(back_populates="verification_tokens")

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None or self.attempts >= 5

    def __repr__(self) -> str:
        return (
            f"<VerificationToken id={self.id!r} "
            f"candidate_email={self.candidate_email!r}>"
        )
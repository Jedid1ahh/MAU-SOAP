"""Account email-verification token model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from .user import User


class AccountVerificationToken(db.Model):
    """A hashed, expiring, single-use account verification credential."""

    __tablename__ = "account_verification_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="account_verification_tokens")

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_invalidated(self) -> bool:
        return self.invalidated_at is not None

    def __repr__(self) -> str:
        return (
            f"<AccountVerificationToken id={self.id!r} "
            f"user_id={self.user_id!r}>"
        )

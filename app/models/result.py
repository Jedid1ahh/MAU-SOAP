"""Submission result model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import TimestampMixin, database_enum
from .enums import ResultStatus

if TYPE_CHECKING:
    from .submission import Submission


class Result(TimestampMixin, db.Model):
    """Aggregated marks and release state for one submission."""

    __tablename__ = "results"
    __table_args__ = (
        CheckConstraint("marks_obtained >= 0", name="nonnegative_marks_obtained"),
        CheckConstraint("total_marks >= 0", name="nonnegative_total_marks"),
        CheckConstraint(
            "percentage >= 0 AND percentage <= 100",
            name="percentage_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    marks_obtained: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        server_default="0.00",
    )
    total_marks: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("0.00"),
        server_default="0.00",
    )
    status: Mapped[ResultStatus] = mapped_column(
        database_enum(ResultStatus, "result_status"),
        default=ResultStatus.PENDING_MANUAL_REVIEW,
        server_default=ResultStatus.PENDING_MANUAL_REVIEW.value,
        index=True,
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    submission: Mapped[Submission] = relationship(back_populates="result")

    @property
    def is_released(self) -> bool:
        return self.released_at is not None

    def __repr__(self) -> str:
        return f"<Result id={self.id!r} status={self.status.value!r}>"
"""Supervision violation log model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from .base import JSON_DOCUMENT, JsonObject, database_enum
from .enums import ViolationType

if TYPE_CHECKING:
    from .submission import Submission


class WarningLog(db.Model):
    """One server-recorded integrity warning for an active submission."""

    __tablename__ = "warning_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        index=True,
    )
    violation_type: Mapped[ViolationType] = mapped_column(
        database_enum(ViolationType, "violation_type"),
        index=True,
    )
    message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[JsonObject | None] = mapped_column(
        "metadata",
        MutableDict.as_mutable(JSON_DOCUMENT),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Evidence files are stored outside /static and delivered only through
    # authenticated Admin routes.
    evidence_storage_name: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
    )
    evidence_content_type: Mapped[str | None] = mapped_column(String(100))
    evidence_byte_size: Mapped[int | None] = mapped_column(Integer)
    evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    evidence_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    evidence_ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    evidence_duration_ms: Mapped[int | None] = mapped_column(Integer)
    evidence_uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    evidence_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    submission: Mapped[Submission] = relationship(
        back_populates="warning_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<WarningLog id={self.id!r} "
            f"violation_type={self.violation_type.value!r}>"
        )
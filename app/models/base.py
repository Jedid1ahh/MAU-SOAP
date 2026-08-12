"""Reusable SQLAlchemy types and mixins for the model layer."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, DateTime, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# MariaDB receives native JSON, PostgreSQL receives JSONB, and SQLite receives
# JSON during isolated unit tests.
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


def database_enum(enum_class: type[Enum], name: str) -> SqlEnum:
    """Create a named enum that stores member values rather than Python names."""

    return SqlEnum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        native_enum=True,
        create_constraint=True,
        validate_strings=True,
    )


class TimestampMixin:
    """Add server-maintained creation and modification timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


JsonObject = dict[str, Any]
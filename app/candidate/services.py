"""Shared time and credential helpers for examination sessions."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from flask import current_app


def utc_now() -> datetime:
    """Return an aware UTC time for deterministic tests."""

    return datetime.now(UTC)


def aware_utc(value: datetime) -> datetime:
    """Normalize timestamps that may lose timezone metadata."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def credential_digest(raw_value: str) -> str:
    """Create a keyed digest for verification credentials."""

    secret_key = str(
        current_app.config["SECRET_KEY"]
    ).encode("utf-8")

    return hmac.new(
        secret_key,
        raw_value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

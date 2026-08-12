"""Password-reset token and email services."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from flask import current_app, render_template, url_for
from flask_mail import Message
from sqlalchemy import select

from app.extensions import db, mail
from app.models import PasswordResetToken, User


def token_digest(raw_token: str) -> str:
    """Return the irreversible database representation of a reset token."""

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    """Return an aware UTC time, isolated for deterministic tests."""

    return datetime.now(UTC)


def _aware_utc(value: datetime) -> datetime:
    """Normalize timestamps returned by databases that drop timezone metadata."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def create_reset_token(user: User) -> tuple[str, PasswordResetToken]:
    """Invalidate older links and create one CSPRNG reset credential."""

    now = utc_now()
    active_tokens = db.session.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.locked_at.is_(None),
        )
    )
    for previous_token in active_tokens:
        previous_token.locked_at = now

    raw_token = secrets.token_urlsafe(32)
    lifetime = int(current_app.config["PASSWORD_RESET_MAX_AGE_MINUTES"])
    reset_token = PasswordResetToken(
        user=user,
        token_hash=token_digest(raw_token),
        expires_at=now + timedelta(minutes=lifetime),
    )
    db.session.add(reset_token)
    return raw_token, reset_token


def resolve_reset_token(raw_token: str) -> PasswordResetToken | None:
    """Return a reset token only while it is unused, unlocked, and unexpired."""

    reset_token = db.session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_digest(raw_token)
        )
    )
    if reset_token is None or reset_token.is_used or reset_token.is_locked:
        return None
    if _aware_utc(reset_token.expires_at) <= utc_now():
        return None
    return reset_token


def send_reset_email(user: User, raw_token: str) -> None:
    """Email the time-limited reset link to the configured Admin."""

    reset_url = url_for(
        "admin.reset_password",
        token=raw_token,
        _external=True,
    )
    message = Message(
        subject="Reset your MAU-SOAP Admin password",
        recipients=[user.email],
        body=render_template(
            "emails/password_reset.txt",
            reset_url=reset_url,
        ),
        html=render_template(
            "emails/password_reset.html",
            reset_url=reset_url,
        ),
    )
    mail.send(message)
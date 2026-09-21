"""Security and email services for institutional account verification."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from flask import current_app, render_template, url_for
from flask_mail import Message
from sqlalchemy import select

from app.extensions import db, mail
from app.models import AccountVerificationToken, User


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def aware_utc(value: datetime) -> datetime:
    """Restore UTC metadata when a database returns a naive timestamp."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def token_digest(raw_token: str) -> str:
    """Return an irreversible representation of a verification token."""

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_account_verification(
    user: User,
) -> tuple[str, AccountVerificationToken]:
    """Invalidate older links and issue one new verification credential."""

    now = utc_now()
    active_tokens = db.session.scalars(
        select(AccountVerificationToken).where(
            AccountVerificationToken.user_id == user.id,
            AccountVerificationToken.used_at.is_(None),
            AccountVerificationToken.invalidated_at.is_(None),
        )
    )
    for previous_token in active_tokens:
        previous_token.invalidated_at = now

    raw_token = secrets.token_urlsafe(32)
    lifetime = int(
        current_app.config["ACCOUNT_VERIFICATION_MAX_AGE_MINUTES"]
    )
    verification = AccountVerificationToken(
        user=user,
        token_hash=token_digest(raw_token),
        expires_at=now + timedelta(minutes=lifetime),
    )
    db.session.add(verification)
    return raw_token, verification


def resolve_account_verification(
    raw_token: str,
) -> AccountVerificationToken | None:
    """Resolve one unused, active, unexpired verification link."""

    verification = db.session.scalar(
        select(AccountVerificationToken).where(
            AccountVerificationToken.token_hash == token_digest(raw_token)
        )
    )
    if (
        verification is None
        or verification.is_used
        or verification.is_invalidated
        or aware_utc(verification.expires_at) <= utc_now()
    ):
        return None
    return verification


def send_account_verification_email(user: User, raw_token: str) -> None:
    """Email a single-use verification link to a new account."""

    verification_url = url_for(
        "accounts.verify_email",
        token=raw_token,
        _external=True,
    )
    message = Message(
        subject="Verify your MAU-SOAP account",
        recipients=[user.email],
        body=render_template(
            "emails/account_verification.txt",
            user=user,
            verification_url=verification_url,
        ),
        html=render_template(
            "emails/account_verification.html",
            user=user,
            verification_url=verification_url,
        ),
    )
    if current_app.config["MAIL_SUPPRESS_SEND"]:
        current_app.logger.info(
            "Development account verification for %s: %s",
            user.email,
            verification_url,
        )
    mail.send(message)

"""Security and email services for Candidate verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from flask import current_app, render_template, url_for
from flask_mail import Message
from sqlalchemy import select

from app.extensions import db, mail
from app.models import Exam, VerificationToken


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


def create_verification(
    exam: Exam,
    candidate_name: str,
    candidate_email: str,
) -> tuple[str, str, VerificationToken]:
    """Create a fresh OTP and magic-link pair."""

    now = utc_now()
    normalized_email = candidate_email.strip().lower()

    pending_tokens = db.session.scalars(
        select(VerificationToken).where(
            VerificationToken.exam_id == exam.id,
            VerificationToken.candidate_email
            == normalized_email,
            VerificationToken.verified_at.is_(None),
            VerificationToken.locked_at.is_(None),
        )
    )

    for previous_token in pending_tokens:
        previous_token.locked_at = now

    raw_otp = f"{secrets.randbelow(1_000_000):06d}"
    raw_magic_token = secrets.token_urlsafe(32)

    lifetime = int(
        current_app.config[
            "CANDIDATE_VERIFICATION_MAX_AGE_MINUTES"
        ]
    )

    verification = VerificationToken(
        exam=exam,
        candidate_name=candidate_name.strip(),
        candidate_email=normalized_email,
        otp_hash=credential_digest(raw_otp),
        magic_token_hash=credential_digest(
            raw_magic_token
        ),
        expires_at=now + timedelta(minutes=lifetime),
    )

    db.session.add(verification)

    return raw_otp, raw_magic_token, verification


def verification_is_expired(
    verification: VerificationToken,
) -> bool:
    """Determine whether verification has expired."""

    return (
        aware_utc(verification.expires_at)
        <= utc_now()
    )


def resolve_magic_token(
    exam: Exam,
    raw_magic_token: str,
) -> VerificationToken | None:
    """Resolve an unused and unexpired magic link."""

    verification = db.session.scalar(
        select(VerificationToken).where(
            VerificationToken.exam_id == exam.id,
            VerificationToken.magic_token_hash
            == credential_digest(raw_magic_token),
        )
    )

    if (
        verification is None
        or verification.is_locked
        or verification.verified_at is not None
        or verification_is_expired(verification)
    ):
        return None

    return verification


def verify_otp(
    verification: VerificationToken,
    raw_otp: str,
) -> bool:
    """Compare an OTP in constant time."""

    return hmac.compare_digest(
        verification.otp_hash,
        credential_digest(raw_otp),
    )


def register_failed_attempt(
    verification: VerificationToken,
) -> None:
    """Increment failures and lock the fifth attempt."""

    verification.attempts = min(
        verification.attempts + 1,
        5,
    )

    if verification.attempts >= 5:
        verification.locked_at = utc_now()


def complete_verification(
    verification: VerificationToken,
) -> str:
    """Complete verification and issue Candidate access."""

    now = utc_now()

    sibling_tokens = db.session.scalars(
        select(VerificationToken).where(
            VerificationToken.exam_id
            == verification.exam_id,
            VerificationToken.candidate_email
            == verification.candidate_email,
            VerificationToken.id != verification.id,
            VerificationToken.locked_at.is_(None),
        )
    )

    for sibling in sibling_tokens:
        sibling.locked_at = now

    raw_session_token = secrets.token_urlsafe(32)

    session_lifetime = int(
        current_app.config[
            "CANDIDATE_SESSION_MAX_AGE_MINUTES"
        ]
    )

    verification.verified_at = now
    verification.session_token_hash = (
        credential_digest(raw_session_token)
    )
    verification.expires_at = (
        now + timedelta(minutes=session_lifetime)
    )

    return raw_session_token


def resolve_candidate_session(
    exam: Exam,
    raw_session_token: str | None,
) -> VerificationToken | None:
    """Resolve Candidate access to the pre-exam screen."""

    if not raw_session_token:
        return None

    verification = db.session.scalar(
        select(VerificationToken).where(
            VerificationToken.exam_id == exam.id,
            VerificationToken.session_token_hash
            == credential_digest(raw_session_token),
            VerificationToken.verified_at.is_not(None),
            VerificationToken.locked_at.is_(None),
        )
    )

    if (
        verification is None
        or verification_is_expired(verification)
    ):
        return None

    return verification


def send_verification_email(
    verification: VerificationToken,
    raw_otp: str,
    raw_magic_token: str,
) -> None:
    """Email both supported verification methods."""

    magic_url = url_for(
        "candidate.verify_magic_link",
        token=verification.exam.exam_link_token,
        magic_token=raw_magic_token,
        _external=True,
    )

    message = Message(
        subject=(
            f"Verify access to "
            f"{verification.exam.title}"
        ),
        recipients=[verification.candidate_email],
        body=render_template(
            "emails/candidate_verification.txt",
            verification=verification,
            otp=raw_otp,
            magic_url=magic_url,
        ),
        html=render_template(
            "emails/candidate_verification.html",
            verification=verification,
            otp=raw_otp,
            magic_url=magic_url,
        ),
    )

    if current_app.config["MAIL_SUPPRESS_SEND"]:
        current_app.logger.info(
            (
                "Development Candidate verification "
                "for %s: OTP %s; link %s"
            ),
            verification.candidate_email,
            raw_otp,
            magic_url,
        )

    mail.send(message)
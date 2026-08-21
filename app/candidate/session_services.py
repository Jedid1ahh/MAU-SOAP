"""Server-authoritative Candidate examination-session services."""

from __future__ import annotations

import hmac
import math
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Exam, Submission, VerificationToken

from .services import aware_utc, credential_digest, utc_now


class ExistingAttemptError(Exception):
    """Raised when a different session already owns the Candidate attempt."""


class FinalizedSubmissionError(Exception):
    """Raised when code attempts to change a finalized submission."""


def resolve_submission_session(
    exam: Exam,
    raw_session_token: str | None,
) -> Submission | None:
    """Resolve a started Candidate submission from its raw session token."""

    if not raw_session_token:
        return None
    return db.session.scalar(
        select(Submission).where(
            Submission.exam_id == exam.id,
            Submission.resume_token_hash
            == credential_digest(raw_session_token),
        )
    )


def start_submission(
    exam: Exam,
    verification: VerificationToken,
    raw_session_token: str,
) -> tuple[Submission, bool]:
    """Create exactly one server-started attempt, or resume the same token."""

    session_token_hash = credential_digest(raw_session_token)
    existing = db.session.scalar(
        select(Submission).where(
            Submission.exam_id == exam.id,
            Submission.candidate_email == verification.candidate_email,
        )
    )
    if existing is not None:
        if not secrets_match(existing.resume_token_hash, session_token_hash):
            raise ExistingAttemptError
        return existing, False

    started_at = utc_now()
    submission = Submission(
        exam=exam,
        candidate_name=verification.candidate_name,
        candidate_email=verification.candidate_email,
        responses={},
        resume_token_hash=session_token_hash,
        started_at=started_at,
        supervision_consent_at=started_at,
        warn_count=0,
    )
    db.session.add(submission)
    try:
        db.session.flush()
    except IntegrityError as error:
        db.session.rollback()
        concurrent = db.session.scalar(
            select(Submission).where(
                Submission.exam_id == exam.id,
                Submission.candidate_email == verification.candidate_email,
            )
        )
        if concurrent is None or not secrets_match(
            concurrent.resume_token_hash,
            session_token_hash,
        ):
            raise ExistingAttemptError from error
        return concurrent, False
    return submission, True


def secrets_match(stored_digest: str, candidate_digest: str) -> bool:
    """Compare session-token digests without timing-dependent equality."""

    return hmac.compare_digest(stored_digest, candidate_digest)


def submission_deadline(submission: Submission) -> datetime:
    """Return the UTC deadline derived only from the server start time."""

    return aware_utc(submission.started_at) + timedelta(
        minutes=submission.exam.time_limit_minutes
    )


def remaining_seconds(
    submission: Submission,
    *,
    now: datetime | None = None,
) -> int:
    """Return a nonnegative, rounded-up server-authoritative countdown."""

    current_time = aware_utc(now) if now is not None else utc_now()
    seconds = (submission_deadline(submission) - current_time).total_seconds()
    return max(0, math.ceil(seconds))


def finalize_expired_submission(submission: Submission) -> bool:
    """Finalize an expired attempt without accepting late browser changes."""

    if submission.is_finalized:
        return True
    if remaining_seconds(submission) > 0:
        return False
    submission.submitted_at = utc_now()
    submission.submission_reason = "time_expired"
    return True


def save_submission_progress(
    submission: Submission,
    responses: dict[str, str],
) -> None:
    """Persist validated answers without finalizing the active attempt."""

    if submission.is_finalized:
        raise FinalizedSubmissionError
    if remaining_seconds(submission) <= 0:
        finalize_expired_submission(submission)
        raise FinalizedSubmissionError

    submission.responses = responses
    submission.last_saved_at = utc_now()


def finalize_submission(
    submission: Submission,
    responses: dict[str, str],
) -> None:
    """Store the one accepted manual submission and lock future writes."""

    if submission.is_finalized:
        raise FinalizedSubmissionError
    if remaining_seconds(submission) <= 0:
        finalize_expired_submission(submission)
        raise FinalizedSubmissionError

    submitted_at = utc_now()
    submission.responses = responses
    submission.last_saved_at = submitted_at
    submission.submitted_at = submitted_at
    submission.submission_reason = "manual"


def finalize_warning_limit(
    submission: Submission,
    responses: dict[str, str],
) -> None:
    """Finalize an active attempt after its third integrity warning."""

    if submission.is_finalized:
        return
    if remaining_seconds(submission) <= 0:
        finalize_expired_submission(submission)
        return

    submitted_at = utc_now()
    submission.responses = responses
    submission.last_saved_at = submitted_at
    submission.submitted_at = submitted_at
    submission.submission_reason = "warning_limit"
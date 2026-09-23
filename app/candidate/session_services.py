"""Server-authoritative Candidate examination-session services."""

from __future__ import annotations

import hmac
import math
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.grading import grade_submission
from app.models import (
    CourseEnrollment,
    EnrollmentStatus,
    Exam,
    ExamAccommodation,
    Role,
    Submission,
    User,
)

from .services import aware_utc, credential_digest, utc_now


class ExistingAttemptError(Exception):
    """Raised when a different session already owns the Candidate attempt."""


class FinalizedSubmissionError(Exception):
    """Raised when code attempts to change a finalized submission."""


class AttemptLimitReachedError(Exception):
    """Raised when a Student has used every allowed attempt."""


class ExamUnavailableError(Exception):
    """Raised when an examination is outside its configured window."""


def exam_availability(exam: Exam, *, now: datetime | None = None) -> str:
    """Return available, upcoming, or closed from server-controlled UTC time."""

    current_time = aware_utc(now) if now is not None else utc_now()
    if exam.opens_at is not None and current_time < aware_utc(exam.opens_at):
        return "upcoming"
    if exam.closes_at is not None and current_time >= aware_utc(exam.closes_at):
        return "closed"
    return "available"


def student_can_access_exam(exam: Exam, student: User) -> bool:
    """Return whether an active Student accepted the exam's course invite."""

    if student.role is not Role.STUDENT or not student.can_access_portal:
        return False
    return (
        db.session.scalar(
            select(CourseEnrollment.id).where(
                CourseEnrollment.course_id == exam.course_id,
                CourseEnrollment.student_id == student.id,
                CourseEnrollment.status == EnrollmentStatus.ACCEPTED,
            )
        )
        is not None
    )


def submission_for_student(exam: Exam, student: User) -> Submission | None:
    """Resolve the logged-in Student's latest attempt for an examination."""

    return db.session.scalar(
        select(Submission)
        .where(
            Submission.exam_id == exam.id,
            Submission.candidate_email == student.email,
        )
        .order_by(Submission.attempt_number.desc())
    )


def resolve_submission_session(
    exam: Exam,
    raw_session_token: str | None,
) -> Submission | None:
    """Resolve a legacy browser-resume credential without authorizing a route."""

    if not raw_session_token:
        return None
    return db.session.scalar(
        select(Submission).where(
            Submission.exam_id == exam.id,
            Submission.resume_token_hash == credential_digest(raw_session_token),
        )
    )


def start_submission(
    exam: Exam,
    student: User | object,
    raw_session_token: str | None = None,
) -> tuple[Submission, bool]:
    """Create exactly one server-started attempt, or resume that Student."""

    candidate_email = (
        str(getattr(student, "email", None) or student.candidate_email)
        .strip()
        .casefold()
    )
    candidate_name = str(
        getattr(student, "full_name", None)
        or getattr(student, "candidate_name", None)
        or candidate_email
    )
    session_token_hash = credential_digest(
        raw_session_token or secrets.token_urlsafe(32)
    )
    attempts = db.session.scalars(
        select(Submission)
        .where(
            Submission.exam_id == exam.id,
            Submission.candidate_email == candidate_email,
        )
        .order_by(Submission.attempt_number.desc())
    ).all()
    existing = next((item for item in attempts if not item.is_finalized), None)
    if existing is not None:
        if raw_session_token is not None and not secrets_match(
            existing.resume_token_hash,
            session_token_hash,
        ):
            raise ExistingAttemptError
        return existing, False

    if exam_availability(exam) != "available":
        raise ExamUnavailableError(exam_availability(exam))
    if len(attempts) >= exam.attempt_limit:
        return attempts[0], False

    started_at = utc_now()
    question_order = [question.id for question in exam.questions]
    randomizer = secrets.SystemRandom()
    if exam.shuffle_questions:
        randomizer.shuffle(question_order)
    option_orders = {}
    for question in exam.questions:
        if question.options:
            option_keys = list(question.options)
            if exam.shuffle_options:
                randomizer.shuffle(option_keys)
            option_orders[str(question.id)] = option_keys
    submission = Submission(
        exam=exam,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        attempt_number=(attempts[0].attempt_number + 1 if attempts else 1),
        responses={},
        question_order=question_order,
        option_orders=option_orders,
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
            select(Submission)
            .where(
                Submission.exam_id == exam.id,
                Submission.candidate_email == candidate_email,
            )
            .order_by(Submission.attempt_number.desc())
        )
        if concurrent is None or (
            raw_session_token is not None
            and not secrets_match(
                concurrent.resume_token_hash,
                session_token_hash,
            )
        ):
            raise ExistingAttemptError from error
        return concurrent, False
    return submission, True


def secrets_match(stored_digest: str, candidate_digest: str) -> bool:
    """Compare stored credential digests without timing-dependent equality."""

    return hmac.compare_digest(stored_digest, candidate_digest)


def submission_deadline(submission: Submission) -> datetime:
    """Return the UTC deadline derived only from the server start time."""

    student_id = db.session.scalar(
        select(User.id).where(User.email == submission.candidate_email)
    )
    extra_minutes = 0
    if student_id is not None:
        extra_minutes = (
            db.session.scalar(
                select(ExamAccommodation.extra_time_minutes).where(
                    ExamAccommodation.exam_id == submission.exam_id,
                    ExamAccommodation.student_id == student_id,
                )
            )
            or 0
        )
    deadline = aware_utc(submission.started_at) + timedelta(
        minutes=submission.exam.time_limit_minutes + extra_minutes
    )
    if submission.exam.closes_at is not None:
        deadline = min(deadline, aware_utc(submission.exam.closes_at))
    return deadline


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
        grade_submission(submission)
        return True
    if remaining_seconds(submission) > 0:
        return False
    submission.submitted_at = utc_now()
    submission.submission_reason = "time_expired"
    grade_submission(submission)
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
    grade_submission(submission)


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
    grade_submission(submission)

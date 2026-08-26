"""Server-authoritative result release policy services."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import ReleaseOption, Result, ResultStatus


class ResultNotCompleteError(ValueError):
    """Raised when an incomplete result is manually released."""


def utc_now() -> datetime:
    """Return one timezone-aware UTC timestamp for release decisions."""

    return datetime.now(UTC)


def aware_utc(value: datetime) -> datetime:
    """Normalize timestamps returned without timezone metadata by MariaDB."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def synchronize_result_release(
    result: Result,
    *,
    now: datetime | None = None,
) -> bool:
    """Release an eligible result according to its examination policy."""

    if result.status is not ResultStatus.COMPLETE:
        return False
    if result.released_at is not None:
        return True

    current_time = aware_utc(now) if now is not None else utc_now()
    exam = result.submission.exam
    release_is_due = exam.release_option is ReleaseOption.IMMEDIATE
    if exam.release_option is ReleaseOption.SCHEDULED:
        release_is_due = (
            exam.scheduled_release_at is not None
            and aware_utc(exam.scheduled_release_at) <= current_time
        )

    if release_is_due:
        result.released_at = current_time
        return True
    return False


def release_result_now(
    result: Result,
    *,
    now: datetime | None = None,
) -> None:
    """Allow the owning Admin to release one completed result early."""

    if result.status is not ResultStatus.COMPLETE:
        raise ResultNotCompleteError(
            "Complete every pending manual grade before releasing this result."
        )
    if result.released_at is None:
        result.released_at = aware_utc(now) if now is not None else utc_now()
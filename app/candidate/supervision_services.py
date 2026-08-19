"""Server-side validation and persistence for Candidate supervision events."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import (
    MonitorType,
    Submission,
    ViolationType,
    WarningLog,
)

from .services import aware_utc, utc_now

WARNING_LIMIT = 3
EVENT_COOLDOWN_SECONDS = 3

WARNING_MESSAGES = {
    ViolationType.COPY_PASTE: (
        "Copying, cutting, pasting, and context menus are disabled "
        "during the examination."
    ),
    ViolationType.SCREENSHOT_ATTEMPT: (
        "A likely screenshot keyboard shortcut was detected."
    ),
    ViolationType.FOCUS_LOSS: (
        "The examination window lost focus or was hidden."
    ),
    ViolationType.FACE_NOT_DETECTED: (
        "Your face could not be detected by the examination monitor."
    ),
    ViolationType.GAZE_DEVIATION: (
        "Your gaze moved outside the permitted examination area."
    ),
}

ALLOWED_METADATA_FIELDS = {
    "duration_ms",
    "gaze_ratio",
    "shortcut",
    "source",
    "visibility_state",
    "recording_supported",
}


class WarningLimitReachedError(Exception):
    """Raised when an active submission already has three warnings."""


class InvalidViolationError(Exception):
    """Raised when a browser reports an unsupported supervision event."""


def violation_type_for_exam(
    raw_value: object,
    monitor_type: MonitorType,
) -> ViolationType:
    """Validate one client-reported violation against the exam settings."""

    if not isinstance(raw_value, str):
        raise InvalidViolationError

    try:
        violation_type = ViolationType(raw_value)
    except ValueError as error:
        raise InvalidViolationError from error

    if (
        violation_type is ViolationType.GAZE_DEVIATION
        and monitor_type is not MonitorType.EYE_GAZE
    ):
        raise InvalidViolationError

    return violation_type


def sanitize_metadata(
    raw_metadata: object,
) -> dict[str, Any] | None:
    """Keep only small scalar diagnostic values, never webcam imagery."""

    if raw_metadata is None:
        return None

    if not isinstance(raw_metadata, dict):
        raise InvalidViolationError

    sanitized: dict[str, Any] = {}

    for key in ALLOWED_METADATA_FIELDS:
        value = raw_metadata.get(key)

        if isinstance(value, str):
            sanitized[key] = value[:100]
        elif isinstance(value, bool):
            sanitized[key] = value
        elif (
            isinstance(value, (int, float))
            and math.isfinite(value)
        ):
            sanitized[key] = value

    return sanitized or None


def record_warning(
    submission: Submission,
    violation_type: ViolationType,
    raw_metadata: object = None,
    *,
    now: datetime | None = None,
) -> tuple[WarningLog, bool]:
    """Persist one debounced event and increment the fixed warning counter."""

    if submission.warn_count >= WARNING_LIMIT:
        raise WarningLimitReachedError

    occurred_at = (
        aware_utc(now)
        if now is not None
        else utc_now()
    )

    latest = db.session.scalar(
        select(WarningLog)
        .where(
            WarningLog.submission_id == submission.id,
            WarningLog.violation_type == violation_type,
        )
        .order_by(WarningLog.occurred_at.desc())
        .limit(1)
    )

    if (
        latest is not None
        and aware_utc(latest.occurred_at)
        >= occurred_at
        - timedelta(seconds=EVENT_COOLDOWN_SECONDS)
    ):
        return latest, False

    warning = WarningLog(
        submission=submission,
        violation_type=violation_type,
        message=WARNING_MESSAGES[violation_type],
        metadata_json=sanitize_metadata(
            raw_metadata
        ),
        occurred_at=occurred_at,
    )

    submission.warn_count += 1
    db.session.add(warning)
    db.session.flush()

    return warning, True
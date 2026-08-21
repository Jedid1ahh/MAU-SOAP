"""Validation and protected storage for face-absence video evidence."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from flask import current_app
from sqlalchemy import select
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import WarningLog

from .services import aware_utc, utc_now

ALLOWED_VIDEO_TYPES = {
    "video/webm": ".webm",
    "video/mp4": ".mp4",
}


class InvalidEvidenceError(Exception):
    """Raised when an evidence upload is malformed or unsafe."""


class EvidenceTooLargeError(Exception):
    """Raised when an evidence upload exceeds the configured byte limit."""


def evidence_directory() -> Path:
    """Return the private server directory used for supervision evidence."""

    configured = current_app.config.get("SUPERVISION_EVIDENCE_DIR")
    directory = (
        Path(configured)
        if configured
        else Path(current_app.instance_path) / "supervision_evidence"
    )
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def _client_datetime(raw_value: object) -> datetime:
    if not isinstance(raw_value, str) or len(raw_value) > 64:
        raise InvalidEvidenceError

    try:
        parsed = datetime.fromisoformat(
            raw_value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise InvalidEvidenceError from error

    if parsed.tzinfo is None:
        raise InvalidEvidenceError

    return parsed.astimezone(UTC)


def _duration(raw_value: object) -> int:
    try:
        duration_ms = int(str(raw_value))
    except (TypeError, ValueError) as error:
        raise InvalidEvidenceError from error

    maximum = int(
        current_app.config[
            "SUPERVISION_EVIDENCE_MAX_DURATION_SECONDS"
        ]
    ) * 1000

    if duration_ms <= 0 or duration_ms > maximum:
        raise InvalidEvidenceError

    return duration_ms


def _write_private_file(
    upload: FileStorage,
    extension: str,
) -> tuple[str, int, str]:
    """Stream one upload to an unguessable filename while hashing it."""

    directory = evidence_directory()
    storage_name = f"{secrets.token_urlsafe(24)}{extension}"
    destination = directory / storage_name
    temporary = directory / f".{storage_name}.part"
    maximum = int(
        current_app.config["SUPERVISION_EVIDENCE_MAX_BYTES"]
    )
    byte_size = 0
    digest = hashlib.sha256()

    try:
        with temporary.open("xb") as output:
            while chunk := upload.stream.read(64 * 1024):
                byte_size += len(chunk)

                if byte_size > maximum:
                    raise EvidenceTooLargeError

                digest.update(chunk)
                output.write(chunk)

        if byte_size == 0:
            raise InvalidEvidenceError

        os.replace(temporary, destination)

    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise

    return storage_name, byte_size, digest.hexdigest()


def attach_face_absence_evidence(
    warning: WarningLog,
    upload: FileStorage | None,
    form: dict,
) -> Path:
    """Validate, store, and attach one video clip to its warning log."""

    if warning.evidence_storage_name is not None:
        raise InvalidEvidenceError

    if upload is None:
        raise InvalidEvidenceError

    content_type = (upload.mimetype or "").casefold()
    extension = ALLOWED_VIDEO_TYPES.get(content_type)

    if extension is None:
        raise InvalidEvidenceError

    started_at = _client_datetime(form.get("started_at"))
    ended_at = _client_datetime(form.get("ended_at"))
    duration_ms = _duration(form.get("duration_ms"))

    if ended_at <= started_at:
        raise InvalidEvidenceError

    measured_ms = int(
        (ended_at - started_at).total_seconds() * 1000
    )

    if abs(measured_ms - duration_ms) > 5000:
        raise InvalidEvidenceError

    storage_name, byte_size, digest = _write_private_file(
        upload,
        extension,
    )

    warning.evidence_storage_name = storage_name
    warning.evidence_content_type = content_type
    warning.evidence_byte_size = byte_size
    warning.evidence_sha256 = digest
    warning.evidence_started_at = started_at
    warning.evidence_ended_at = ended_at
    warning.evidence_duration_ms = duration_ms
    warning.evidence_uploaded_at = utc_now()

    return evidence_directory() / storage_name


def purge_expired_evidence(
    *,
    now: datetime | None = None,
) -> int:
    """Delete clips older than the configured retention period."""

    current_time = aware_utc(now) if now is not None else utc_now()
    retention_days = int(
        current_app.config[
            "SUPERVISION_EVIDENCE_RETENTION_DAYS"
        ]
    )
    cutoff = current_time - timedelta(days=retention_days)

    expired = db.session.scalars(
        select(WarningLog).where(
            WarningLog.evidence_storage_name.is_not(None),
            WarningLog.evidence_uploaded_at.is_not(None),
            WarningLog.evidence_uploaded_at < cutoff,
        )
    ).all()

    directory = evidence_directory()

    for warning in expired:
        (
            directory / warning.evidence_storage_name
        ).unlink(missing_ok=True)

        warning.evidence_storage_name = None
        warning.evidence_content_type = None
        warning.evidence_byte_size = None
        warning.evidence_sha256 = None
        warning.evidence_deleted_at = current_time

    return len(expired)
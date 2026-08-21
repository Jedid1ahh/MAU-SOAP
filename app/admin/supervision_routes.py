"""Authenticated Admin supervision feed and evidence delivery."""

from __future__ import annotations

from pathlib import Path

from flask import (
    abort,
    jsonify,
    make_response,
    send_file,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func, select
from werkzeug.utils import secure_filename

from app.candidate.evidence_services import (
    evidence_directory,
    purge_expired_evidence,
)
from app.extensions import db
from app.models import (
    Exam,
    Submission,
    ViolationType,
    WarningLog,
)

from . import admin_bp
from .auth import admin_required


def _owned_warning(warning_id: int) -> WarningLog:
    warning = db.session.scalar(
        select(WarningLog)
        .join(WarningLog.submission)
        .join(Submission.exam)
        .where(
            WarningLog.id == warning_id,
            Exam.admin_id == current_user.id,
        )
    )

    if warning is None:
        abort(404)

    return warning


def _evidence_path(warning: WarningLog) -> Path:
    if not warning.evidence_storage_name:
        abort(404)

    directory = evidence_directory().resolve()
    path = (
        directory / warning.evidence_storage_name
    ).resolve()

    if (
        path.parent != directory or
        not path.is_file()
    ):
        abort(404)

    return path


def _evidence_status(
    warning: WarningLog,
) -> str | None:
    if (
        warning.violation_type
        is not ViolationType.FACE_NOT_DETECTED
    ):
        return None

    if warning.evidence_deleted_at is not None:
        return "expired"

    if warning.evidence_storage_name:
        return "available"

    metadata = warning.metadata_json or {}

    return (
        "recording"
        if metadata.get("recording_supported")
        else "unavailable"
    )


def _warning_sequence(
    warning: WarningLog,
) -> int:
    """Return this event's stable position within its submission warnings."""

    count = db.session.scalar(
        select(
            func.count(WarningLog.id)
        ).where(
            WarningLog.submission_id
            == warning.submission_id,
            WarningLog.id
            <= warning.id,
        )
    )

    return int(count)

def _event_payload(warning: WarningLog) -> dict:
    submission = warning.submission
    exam = submission.exam
    available = bool(
        warning.evidence_storage_name
    )

    return {
        "id": warning.id,
        "candidate_name": submission.candidate_name,
        "candidate_email": submission.candidate_email,
        "exam_title": exam.title,
        "course_code": exam.course_code,
        "violation_type":
            warning.violation_type.value,
        "message": warning.message,
        "occurred_at":
            warning.occurred_at.isoformat(),
        "warning_count": _warning_sequence(
            warning
        ),
        "evidence_status":
            _evidence_status(warning),
        "evidence": (
            {
                "started_at":
                    warning.evidence_started_at.isoformat(),
                "ended_at":
                    warning.evidence_ended_at.isoformat(),
                "duration_ms":
                    warning.evidence_duration_ms,
                "byte_size":
                    warning.evidence_byte_size,
                "uploaded_at":
                    warning.evidence_uploaded_at.isoformat(),
                "view_url": url_for(
                    "admin.view_supervision_evidence",
                    warning_id=warning.id,
                ),
                "download_url": url_for(
                    "admin.download_supervision_evidence",
                    warning_id=warning.id,
                ),
            }
            if available
            else None
        ),
    }


@admin_bp.get("/supervision/events")
@admin_required
def supervision_events():
    """Return warnings for near-real-time dashboard polling."""

    if purge_expired_evidence():
        db.session.commit()

    warnings = db.session.scalars(
        select(WarningLog)
        .join(WarningLog.submission)
        .join(Submission.exam)
        .where(
            Exam.admin_id == current_user.id
        )
        .order_by(WarningLog.id.desc())
        .limit(50)
    ).all()

    return jsonify(
        events=[
            _event_payload(warning)
            for warning in warnings
        ]
    )


def _serve_evidence(
    warning_id: int,
    *,
    download: bool,
):
    warning = _owned_warning(warning_id)
    path = _evidence_path(warning)

    stamp = warning.occurred_at.strftime(
        "%Y%m%dT%H%M%S"
    )
    extension = path.suffix.casefold()

    filename = secure_filename(
        f"{warning.submission.exam.course_code}_"
        f"{warning.submission.candidate_email}_"
        f"{stamp}{extension}"
    )

    response = make_response(
        send_file(
            path,
            mimetype=
                warning.evidence_content_type,
            as_attachment=download,
            download_name=filename,
            conditional=True,
        )
    )

    response.headers["Cache-Control"] = (
        "private, no-store"
    )
    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    return response


@admin_bp.get(
    "/supervision/warnings/"
    "<int:warning_id>/evidence"
)
@admin_required
def view_supervision_evidence(
    warning_id: int,
):
    """Stream private evidence to its owning Admin."""

    return _serve_evidence(
        warning_id,
        download=False,
    )


@admin_bp.get(
    "/supervision/warnings/"
    "<int:warning_id>/evidence/download"
)
@admin_required
def download_supervision_evidence(
    warning_id: int,
):
    """Download private evidence to the Admin computer."""

    return _serve_evidence(
        warning_id,
        download=True,
    )
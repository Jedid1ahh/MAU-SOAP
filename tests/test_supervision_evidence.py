"""Tests for protected face-absence evidence and the Admin live feed."""

from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from app.candidate.evidence_services import (
    InvalidEvidenceError,
    attach_face_absence_evidence,
    evidence_directory,
    purge_expired_evidence,
)
from app.candidate.services import (
    aware_utc,
    credential_digest,
)
from app.extensions import db
from app.models import (
    Exam,
    MonitorType,
    ReleaseOption,
    Submission,
    ViolationType,
    WarningLog,
)


def _active_attempt(client, admin):
    exam = Exam(
        admin_id=admin.id,
        title="Secure Systems",
        course_code="CSC 499",
        course_title="Secure Systems",
        time_limit_minutes=30,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token="evidence-exam",
    )

    raw_token = "evidence-candidate-token"

    submission = Submission(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email="amina@gmail.com",
        responses={},
        resume_token_hash=credential_digest(
            raw_token
        ),
        started_at=datetime.now(UTC),
        supervision_consent_at=datetime.now(UTC),
        warn_count=0,
    )

    db.session.add_all([exam, submission])
    db.session.commit()

    with client.session_transaction() as candidate_session:
        candidate_session[
            f"candidate_access_token_{exam.id}"
        ] = raw_token

    return exam, submission


def _face_warning(
    client,
    exam,
    *,
    recording_supported=True,
):
    response = client.post(
        f"/exam/{exam.exam_link_token}/"
        "session/violations",
        json={
            "violation_type": "face_not_detected",
            "metadata": {
                "source": "mediapipe",
                "recording_supported":
                    recording_supported,
            },
        },
    )

    assert response.status_code == 201

    return response.get_json()["warning_id"]


def _evidence_payload(
    content=b"webm-video-evidence",
    **overrides,
):
    values = {
        "started_at":
            "2026-08-19T10:00:00+00:00",
        "ended_at":
            "2026-08-19T10:00:02+00:00",
        "duration_ms": "2000",
        "video": (
            BytesIO(content),
            "absence.webm",
            "video/webm",
        ),
    }

    values.update(overrides)

    return values


def _login_admin(client):
    response = client.post(
        "/admin/login",
        data={
            "email": "admin@mau.edu.ng",
            "password": "Phase3TestPassword!",
        },
    )

    assert response.status_code == 302


def test_face_absence_evidence_upload_feed_view_and_download(
    client,
    admin,
    app,
):
    exam, submission = _active_attempt(
        client,
        admin,
    )

    client.post(
        f"/exam/{exam.exam_link_token}"
        "/session/violations",
        json={
            "violation_type": "copy_paste",
        },
    )

    client.post(
        f"/exam/{exam.exam_link_token}"
        "/session/violations",
        json={
            "violation_type": "focus_loss",
        },
    )

    warning_id = _face_warning(
        client,
        exam,
    )

    assert submission.is_finalized is True
    assert (
        submission.submission_reason ==
        "warning_limit"
    )

    upload = client.post(
        f"/exam/{exam.exam_link_token}"
        "/session/violations/"
        f"{warning_id}/evidence",
        data=_evidence_payload(),
    )

    warning = db.session.get(
        WarningLog,
        warning_id,
    )

    assert upload.status_code == 201
    assert upload.get_json() == {
        "duration_ms": 2000,
        "evidence_uploaded": True,
        "warning_id": warning_id,
    }

    assert (
        warning.evidence_content_type ==
        "video/webm"
    )
    assert warning.evidence_byte_size == len(
        b"webm-video-evidence"
    )
    assert len(warning.evidence_sha256) == 64
    assert warning.evidence_duration_ms == 2000
    assert (
        warning.evidence_uploaded_at
        is not None
    )
    assert (
        warning.evidence_deleted_at
        is None
    )

    stored = (
        evidence_directory() /
        warning.evidence_storage_name
    )

    assert stored.read_bytes() == (
        b"webm-video-evidence"
    )

    _login_admin(client)

    dashboard = client.get("/admin/")
    feed = client.get(
        "/admin/supervision/events"
    )
    event = feed.get_json()["events"][0]

    assert dashboard.status_code == 200
    assert (
        b"Candidate supervision warnings"
        in dashboard.data
    )
    assert (
        b"admin_supervision.js"
        in dashboard.data
    )
    assert feed.status_code == 200
    assert event["candidate_email"] == (
        submission.candidate_email
    )
    assert (
        event["evidence_status"] ==
        "available"
    )
    assert (
        event["evidence"]["duration_ms"] ==
        2000
    )

    view = client.get(
        event["evidence"]["view_url"]
    )
    download = client.get(
        event["evidence"]["download_url"]
    )

    assert view.status_code == 200
    assert view.data == (
        b"webm-video-evidence"
    )
    assert view.headers["Cache-Control"] == (
        "private, no-store"
    )
    assert (
        view.headers[
            "X-Content-Type-Options"
        ]
        == "nosniff"
    )
    assert (
        "attachment"
        not in view.headers.get(
            "Content-Disposition",
            "",
        )
    )

    assert download.status_code == 200
    assert (
        "attachment"
        in download.headers[
            "Content-Disposition"
        ]
    )

    duplicate = client.post(
        f"/exam/{exam.exam_link_token}"
        "/session/violations/"
        f"{warning_id}/evidence",
        data=_evidence_payload(),
    )

    assert duplicate.status_code == 409

def test_admin_feed_describes_pending_unavailable_and_nonvideo_events(
    client,
    admin,
):
    exam, submission = _active_attempt(
        client,
        admin,
    )

    pending_id = _face_warning(
        client,
        exam,
        recording_supported=True,
    )

    unsupported = WarningLog(
        submission=submission,
        violation_type=
            ViolationType.FACE_NOT_DETECTED,
        message="No face.",
        metadata_json={
            "recording_supported": False
        },
        occurred_at=
            datetime.now(UTC)
            + timedelta(seconds=1),
    )

    clipboard = WarningLog(
        submission=submission,
        violation_type=
            ViolationType.COPY_PASTE,
        message="Clipboard blocked.",
        occurred_at=
            datetime.now(UTC)
            + timedelta(seconds=2),
    )

    submission.warn_count = 3

    db.session.add_all(
        [unsupported, clipboard]
    )
    db.session.commit()

    _login_admin(client)

    events = client.get(
        "/admin/supervision/events"
    ).get_json()["events"]

    by_id = {
        event["id"]: event
        for event in events
    }

    assert (
        by_id[pending_id][
            "evidence_status"
        ]
        == "recording"
    )
    assert (
        by_id[pending_id][
            "warning_count"
        ]
        == 1
    )

    assert (
        by_id[unsupported.id][
            "evidence_status"
        ]
        == "unavailable"
    )
    assert (
        by_id[unsupported.id][
            "warning_count"
        ]
        == 2
    )

    assert (
        by_id[clipboard.id][
            "evidence_status"
        ]
        is None
    )
    assert (
        by_id[clipboard.id][
            "warning_count"
        ]
        == 3
    )
    assert (
        by_id[clipboard.id][
            "evidence"
        ]
        is None
    )


def test_evidence_routes_enforce_candidate_and_admin_ownership(
    client,
    admin,
    app,
):
    exam, submission = _active_attempt(
        client,
        admin,
    )
    warning_id = _face_warning(client, exam)

    with client.session_transaction() as candidate_session:
        candidate_session.pop(
            f"candidate_access_token_{exam.id}"
        )

    no_candidate = client.post(
        f"/exam/{exam.exam_link_token}/"
        f"session/violations/{warning_id}/evidence",
        data=_evidence_payload(),
    )

    assert no_candidate.status_code == 403

    with client.session_transaction() as candidate_session:
        candidate_session[
            f"candidate_access_token_{exam.id}"
        ] = "evidence-candidate-token"

    missing_warning = client.post(
        f"/exam/{exam.exam_link_token}/"
        "session/violations/999999/evidence",
        data=_evidence_payload(),
    )

    assert missing_warning.status_code == 404

    non_face = WarningLog(
        submission=submission,
        violation_type=
            ViolationType.COPY_PASTE,
        message="Clipboard blocked.",
        occurred_at=datetime.now(UTC),
    )

    db.session.add(non_face)
    db.session.commit()

    wrong_type = client.post(
        f"/exam/{exam.exam_link_token}/"
        f"session/violations/{non_face.id}/evidence",
        data=_evidence_payload(),
    )

    assert wrong_type.status_code == 404

    anonymous_admin = app.test_client()

    protected = anonymous_admin.get(
        f"/admin/supervision/warnings/"
        f"{warning_id}/evidence"
    )

    assert protected.status_code == 302
    assert (
        "/admin/login"
        in protected.headers["Location"]
    )

    _login_admin(client)

    missing_admin_warning = client.get(
        "/admin/supervision/warnings/"
        "999999/evidence"
    )

    assert missing_admin_warning.status_code == 404

    absent_evidence = client.get(
        f"/admin/supervision/warnings/"
        f"{warning_id}/evidence"
    )

    assert absent_evidence.status_code == 404

    warning = db.session.get(
        WarningLog,
        warning_id,
    )
    warning.evidence_storage_name = (
        "missing.webm"
    )
    db.session.commit()

    missing_file = client.get(
        f"/admin/supervision/warnings/"
        f"{warning_id}/evidence"
    )

    assert missing_file.status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"video": None},
        {
            "video": (
                BytesIO(b"bad"),
                "bad.txt",
                "text/plain",
            )
        },
        {"started_at": None},
        {"started_at": "x" * 65},
        {"started_at": "not-a-date"},
        {
            "started_at":
                "2026-08-19T10:00:00"
        },
        {"duration_ms": "not-an-integer"},
        {"duration_ms": "0"},
        {"duration_ms": "3600001"},
        {
            "ended_at":
                "2026-08-19T09:59:59+00:00"
        },
        {"duration_ms": "9000"},
        {
            "video": (
                BytesIO(b""),
                "empty.webm",
                "video/webm",
            )
        },
    ],
)
def test_invalid_evidence_uploads_are_rejected(
    client,
    admin,
    changes,
):
    exam, _ = _active_attempt(client, admin)
    warning_id = _face_warning(client, exam)

    payload = _evidence_payload()
    payload.update(changes)

    if payload["video"] is None:
        payload.pop("video")

    response = client.post(
        f"/exam/{exam.exam_link_token}/"
        f"session/violations/{warning_id}/evidence",
        data=payload,
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Invalid evidence upload."
    }


def test_oversized_evidence_is_rejected_and_partial_file_removed(
    client,
    admin,
    app,
):
    app.config[
        "SUPERVISION_EVIDENCE_MAX_BYTES"
    ] = 4

    exam, _ = _active_attempt(client, admin)
    warning_id = _face_warning(client, exam)

    response = client.post(
        f"/exam/{exam.exam_link_token}/"
        f"session/violations/{warning_id}/evidence",
        data=_evidence_payload(
            content=b"too-large"
        ),
    )

    assert response.status_code == 413
    assert list(
        evidence_directory().iterdir()
    ) == []


def test_commit_failure_removes_stored_evidence(
    client,
    admin,
    monkeypatch,
):
    exam, _ = _active_attempt(client, admin)
    warning_id = _face_warning(client, exam)

    def fail_commit():
        raise RuntimeError(
            "database unavailable"
        )

    monkeypatch.setattr(
        db.session,
        "commit",
        fail_commit,
    )

    with pytest.raises(
        RuntimeError,
        match="database unavailable",
    ):
        client.post(
            f"/exam/{exam.exam_link_token}/"
            f"session/violations/"
            f"{warning_id}/evidence",
            data=_evidence_payload(),
        )

    assert list(
        evidence_directory().iterdir()
    ) == []


def test_unexpected_pre_storage_failure_is_propagated(
    client,
    admin,
    monkeypatch,
):
    exam, _ = _active_attempt(client, admin)
    warning_id = _face_warning(client, exam)

    def fail_before_storage(
        *_args,
        **_kwargs,
    ):
        raise RuntimeError(
            "storage unavailable"
        )

    monkeypatch.setattr(
        "app.candidate.session_routes."
        "attach_face_absence_evidence",
        fail_before_storage,
    )

    with pytest.raises(
        RuntimeError,
        match="storage unavailable",
    ):
        client.post(
            f"/exam/{exam.exam_link_token}/"
            f"session/violations/"
            f"{warning_id}/evidence",
            data=_evidence_payload(),
        )


def test_service_rejects_replacing_existing_evidence(
    client,
    admin,
):
    exam, _ = _active_attempt(client, admin)
    warning_id = _face_warning(client, exam)

    warning = db.session.get(
        WarningLog,
        warning_id,
    )
    warning.evidence_storage_name = (
        "already.webm"
    )

    upload = FileStorage(
        stream=BytesIO(b"replacement"),
        filename="replacement.webm",
        content_type="video/webm",
    )

    with pytest.raises(InvalidEvidenceError):
        attach_face_absence_evidence(
            warning,
            upload,
            {},
        )


def test_private_directory_falls_back_to_instance_path(
    app,
):
    app.config[
        "SUPERVISION_EVIDENCE_DIR"
    ] = None

    directory = evidence_directory()

    assert directory == (
        evidence_directory().parent
        / "supervision_evidence"
    )


def test_expired_evidence_is_deleted_and_feed_retains_audit_status(
    client,
    admin,
    monkeypatch,
):
    exam, _ = _active_attempt(client, admin)
    warning_id = _face_warning(client, exam)

    client.post(
        f"/exam/{exam.exam_link_token}/"
        f"session/violations/{warning_id}/evidence",
        data=_evidence_payload(),
    )

    warning = db.session.get(
        WarningLog,
        warning_id,
    )

    stored = (
        evidence_directory()
        / warning.evidence_storage_name
    )

    now = datetime(
        2026,
        10,
        1,
        12,
        0,
        tzinfo=UTC,
    )

    warning.evidence_uploaded_at = (
        now - timedelta(days=31)
    )
    db.session.commit()

    monkeypatch.setattr(
        "app.candidate.evidence_services."
        "utc_now",
        lambda: now,
    )

    _login_admin(client)

    event = client.get(
        "/admin/supervision/events"
    ).get_json()["events"][0]

    assert stored.exists() is False
    assert warning.evidence_storage_name is None
    assert warning.evidence_content_type is None
    assert warning.evidence_byte_size is None
    assert warning.evidence_sha256 is None
    assert (
        aware_utc(
            warning.evidence_deleted_at
        )
        == now
    )
    assert (
        warning.evidence_started_at
        is not None
    )
    assert warning.evidence_duration_ms == 2000
    assert event["evidence_status"] == "expired"
    assert event["evidence"] is None
    assert purge_expired_evidence(
        now=now
    ) == 0


def test_cleanup_supervision_evidence_cli_reports_success_and_failure(
    app,
    monkeypatch,
):
    runner = app.test_cli_runner()

    success = runner.invoke(
        args=[
            "cleanup-supervision-evidence"
        ]
    )

    assert success.exit_code == 0
    assert (
        "Deleted 0 expired"
        in success.output
    )

    def fail_cleanup():
        raise RuntimeError("storage offline")

    monkeypatch.setattr(
        "app.candidate.evidence_services."
        "purge_expired_evidence",
        fail_cleanup,
    )

    failure = runner.invoke(
        args=[
            "cleanup-supervision-evidence"
        ]
    )

    assert failure.exit_code == 1
    assert (
        "cleanup failed: storage offline"
        in failure.output
    )
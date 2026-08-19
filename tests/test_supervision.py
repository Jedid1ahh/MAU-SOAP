"""Tests for Phase 7 Candidate supervision controls and warning logs."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.candidate.services import credential_digest
from app.candidate.supervision_services import (
    InvalidViolationError,
    WarningLimitReachedError,
    record_warning,
    sanitize_metadata,
    violation_type_for_exam,
)
from app.extensions import db
from app.models import (
    Exam,
    MonitorType,
    Question,
    QuestionType,
    ReleaseOption,
    Submission,
    ViolationType,
    WarningLog,
)


def _exam(
    admin,
    *,
    token="supervision-exam",
    monitor_type=MonitorType.FACE,
):
    exam = Exam(
        admin_id=admin.id,
        title="Computer Networks",
        course_code="CSC 408",
        course_title="Computer Networks",
        instructions="Remain in the examination window.",
        time_limit_minutes=30,
        monitor_type=monitor_type,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token=token,
    )

    db.session.add(exam)
    db.session.commit()

    return exam


def _active_submission(
    client,
    exam,
    *,
    raw_token="supervision-session-token",
    started_at=None,
    submitted_at=None,
    submission_reason=None,
):
    submission = Submission(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email="amina@gmail.com",
        responses={},
        resume_token_hash=credential_digest(
            raw_token
        ),
        started_at=(
            started_at
            or datetime.now(UTC)
        ),
        submitted_at=submitted_at,
        submission_reason=submission_reason,
        warn_count=0,
    )

    db.session.add(submission)
    db.session.commit()

    with client.session_transaction() as candidate_session:
        candidate_session[
            f"candidate_access_token_{exam.id}"
        ] = raw_token

    return submission


def _violation_url(exam):
    return (
        f"/exam/{exam.exam_link_token}"
        "/session/violations"
    )


def test_active_session_renders_supervision_ui_and_module(
    client,
    admin,
):
    exam = _exam(admin)
    _active_submission(client, exam)

    page = client.get(
        f"/exam/{exam.exam_link_token}/session"
    )
    script = client.get(
        "/static/js/exam_supervision.js"
    )

    assert page.status_code == 200
    assert (
        b'data-monitor-type="face"'
        in page.data
    )
    assert b"Face presence" in page.data
    assert (
        b"Requesting camera permission"
        in page.data
    )
    assert (
        b"a video-only evidence clip"
        in page.data
    )
    assert b"integrity-warning" in page.data
    assert b"exam_supervision.js" in page.data
    assert (
        b"vendor/mediapipe/vision_bundle.mjs"
        in page.data
    )
    assert (
        b"vendor/mediapipe/wasm"
        in page.data
    )
    assert (
        b"models/face_landmarker.task"
        in page.data
    )

    assert script.status_code == 200
    assert b"getUserMedia" in script.data
    assert b"FaceLandmarker" in script.data
    assert b"visibilitychange" in script.data
    assert b"screenshot_attempt" in script.data
    assert b"copy_paste" in script.data
    assert (
        b"mediapipeModuleUrl"
        in script.data
    )
    assert b"MediaRecorder" in script.data
    assert (
        b"uploadFaceAbsenceEvidence"
        in script.data
    )

def test_eye_gaze_exam_renders_its_configured_monitor(
    client,
    admin,
):
    exam = _exam(
        admin,
        token="gaze-render-exam",
        monitor_type=MonitorType.EYE_GAZE,
    )

    _active_submission(
        client,
        exam,
        raw_token="gaze-render-token",
    )

    page = client.get(
        f"/exam/{exam.exam_link_token}/session"
    )

    assert page.status_code == 200
    assert b'data-monitor-type="eye_gaze"' in page.data
    assert b"Eye and gaze" in page.data


def test_violation_endpoint_requires_matching_active_session(
    client,
    admin,
):
    exam = _exam(admin)

    response = client.post(
        _violation_url(exam),
        json={
            "violation_type": "copy_paste"
        },
    )

    assert response.status_code == 403

    assert response.get_json() == {
        "error": "Candidate session required."
    }

    assert db.session.scalar(
        select(WarningLog)
    ) is None


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {},
        {"json": []},
    ],
)
def test_violation_endpoint_requires_json_object(
    client,
    admin,
    request_kwargs,
):
    exam = _exam(admin)
    _active_submission(client, exam)

    response = client.post(
        _violation_url(exam),
        **request_kwargs,
    )

    assert response.status_code == 400

    assert response.get_json() == {
        "error": "A JSON violation event is required."
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "violation_type": 7
        },
        {
            "violation_type": "unknown"
        },
        {
            "violation_type":
                "gaze_deviation"
        },
        {
            "violation_type": "copy_paste",
            "metadata": [],
        },
    ],
)
def test_violation_endpoint_rejects_invalid_events(
    client,
    admin,
    payload,
):
    exam = _exam(admin)
    _active_submission(client, exam)

    response = client.post(
        _violation_url(exam),
        json=payload,
    )

    assert response.status_code == 400

    assert response.get_json() == {
        "error": "Invalid supervision event."
    }

    assert db.session.scalar(
        select(WarningLog)
    ) is None


def test_violation_is_server_described_logged_and_counted(
    client,
    admin,
):
    exam = _exam(admin)

    submission = _active_submission(
        client,
        exam,
    )

    long_source = (
        "keyboard-"
        + ("x" * 150)
    )

    response = client.post(
        _violation_url(exam),
        json={
            "violation_type":
                "copy_paste",
            "message": (
                "Candidate supplied text "
                "must be ignored."
            ),
            "metadata": {
                "source": long_source,
                "shortcut": "Ctrl+C",
                "duration_ms": 250,
                "unknown":
                    "must not be persisted",
            },
        },
    )

    warning = db.session.scalar(
        select(WarningLog)
    )

    payload = response.get_json()

    assert response.status_code == 201
    assert payload["recorded"] is True
    assert payload["warning_count"] == 1
    assert payload["warning_limit"] == 3

    assert (
        payload["warning_limit_reached"]
        is False
    )

    assert (
        payload["violation_type"]
        == "copy_paste"
    )

    assert "disabled" in payload["message"]
    assert payload["occurred_at"]

    assert (
        warning.submission_id
        == submission.id
    )

    assert (
        warning.violation_type
        is ViolationType.COPY_PASTE
    )

    assert (
        warning.message
        == payload["message"]
    )

    assert (
        "Candidate supplied"
        not in warning.message
    )

    assert warning.metadata_json == {
        "duration_ms": 250,
        "shortcut": "Ctrl+C",
        "source": long_source[:100],
    }

    assert submission.warn_count == 1
    assert response.get_json()["warning_id"] == warning.id


def test_duplicate_event_is_debounced_without_increment(
    client,
    admin,
):
    exam = _exam(admin)

    submission = _active_submission(
        client,
        exam,
    )

    payload = {
        "violation_type": "focus_loss",
        "metadata": {
            "source": "window_blur"
        },
    }

    first = client.post(
        _violation_url(exam),
        json=payload,
    )

    second = client.post(
        _violation_url(exam),
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 200

    assert (
        second.get_json()["recorded"]
        is False
    )

    assert (
        second.get_json()["warning_count"]
        == 1
    )

    assert db.session.scalar(
        select(
            func.count(WarningLog.id)
        )
    ) == 1

    assert submission.warn_count == 1


def test_third_warning_submits_attempt_and_prevents_additional_events(
    client,
    admin,
):
    exam = _exam(admin)

    question = Question(
        exam=exam,
        question_text=(
            "Which protocol is reliable?"
        ),
        question_type=QuestionType.MCQ,
        position=1,
        marks=Decimal("2.00"),
        options={
            "A": "UDP",
            "B": "TCP",
        },
        correct_answer="B",
    )

    db.session.add(question)
    db.session.commit()

    submission = _active_submission(
        client,
        exam,
    )

    for violation_type in (
        "copy_paste",
        "screenshot_attempt",
    ):
        response = client.post(
            _violation_url(exam),
            json={
                "violation_type":
                    violation_type,
            },
        )

        assert response.status_code == 201

    third = client.post(
        _violation_url(exam),
        json={
            "violation_type": "focus_loss",
            "responses": {
                str(question.id): "B",
            },
        },
    )

    fourth = client.post(
        _violation_url(exam),
        json={
            "violation_type":
                "face_not_detected",
        },
    )

    assert third.status_code == 201
    assert (
        third.get_json()["warning_count"] ==
        3
    )
    assert (
        third.get_json()[
            "warning_limit_reached"
        ]
        is True
    )
    assert (
        third.get_json()["submitted"]
        is True
    )
    assert (
        third.get_json()["reason"] ==
        "warning_limit"
    )

    assert fourth.status_code == 409
    assert fourth.get_json() == {
        "reason": "warning_limit",
        "submitted": True,
    }

    assert submission.warn_count == 3
    assert submission.is_finalized is True
    assert (
        submission.submission_reason ==
        "warning_limit"
    )
    assert submission.responses == {
        str(question.id): "B",
    }
    assert db.session.scalar(
        select(func.count(WarningLog.id))
    ) == 3

@pytest.mark.parametrize(
    "case",
    [
        "not-a-dict",
        "unknown-question",
        "non-string",
        "too-long",
        "invalid-mcq",
    ],
)
def test_warning_limit_tolerates_untrusted_response_snapshots(
    client,
    admin,
    case,
):
    exam = _exam(
        admin,
        token=f"snapshot-{case}",
    )

    question = Question(
        exam=exam,
        question_text=(
            "Which protocol is reliable?"
        ),
        question_type=QuestionType.MCQ,
        position=1,
        marks=Decimal("2.00"),
        options={
            "A": "UDP",
            "B": "TCP",
        },
        correct_answer="B",
    )

    db.session.add(question)
    db.session.commit()

    submission = _active_submission(
        client,
        exam,
    )

    responses = {
        "not-a-dict": None,
        "unknown-question": {
            "999999": "ignored",
        },
        "non-string": {
            str(question.id): 7,
        },
        "too-long": {
            str(question.id):
                "x" * 10_001,
        },
        "invalid-mcq": {
            str(question.id): "Z",
        },
    }[case]

    client.post(
        _violation_url(exam),
        json={
            "violation_type": "copy_paste",
        },
    )

    client.post(
        _violation_url(exam),
        json={
            "violation_type":
                "screenshot_attempt",
        },
    )

    client.post(
        _violation_url(exam),
        json={
            "violation_type": "focus_loss",
            "responses": responses,
        },
    )

    assert submission.is_finalized is True

    expected = (
        {}
        if case == "not-a-dict"
        else {str(question.id): ""}
    )

    assert submission.responses == expected

def test_gaze_violation_is_allowed_only_for_eye_gaze_monitor(
    client,
    admin,
):
    exam = _exam(
        admin,
        token="gaze-event-exam",
        monitor_type=MonitorType.EYE_GAZE,
    )

    submission = _active_submission(
        client,
        exam,
        raw_token="gaze-event-token",
    )

    response = client.post(
        _violation_url(exam),
        json={
            "violation_type":
                "gaze_deviation",
            "metadata": {
                "gaze_ratio": 0.91,
                "source": "mediapipe",
            },
        },
    )

    assert response.status_code == 201

    assert (
        response.get_json()[
            "violation_type"
        ]
        == "gaze_deviation"
    )

    assert submission.warn_count == 1


def test_unfinalized_legacy_warning_limit_rejects_more_events(
    client,
    admin,
):
    exam = _exam(
        admin,
        token="legacy-warning-limit",
    )
    submission = _active_submission(
        client,
        exam,
    )

    submission.warn_count = 3
    db.session.commit()

    response = client.post(
        _violation_url(exam),
        json={
            "violation_type": "copy_paste",
        },
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error": (
            "The warning limit has already "
            "been reached."
        ),
        "warning_count": 3,
        "warning_limit": 3,
        "warning_limit_reached": True,
    }

def test_expired_session_is_finalized_before_warning_write(
    client,
    admin,
    monkeypatch,
):
    exam = _exam(admin)

    started_at = datetime(
        2026,
        8,
        18,
        10,
        0,
        tzinfo=UTC,
    )

    submission = _active_submission(
        client,
        exam,
        started_at=started_at,
    )

    monkeypatch.setattr(
        "app.candidate.session_services.utc_now",
        lambda: (
            started_at
            + timedelta(minutes=31)
        ),
    )

    response = client.post(
        _violation_url(exam),
        json={
            "violation_type":
                "face_not_detected"
        },
    )

    assert response.status_code == 409

    assert response.get_json() == {
        "reason": "time_expired",
        "submitted": True,
    }

    assert submission.is_finalized is True

    assert (
        submission.submission_reason
        == "time_expired"
    )

    assert submission.warn_count == 0


def test_metadata_sanitizer_never_accepts_nested_or_nonfinite_values():
    assert sanitize_metadata(None) is None
    assert sanitize_metadata({}) is None

    with pytest.raises(
        InvalidViolationError
    ):
        sanitize_metadata(
            [
                "not",
                "an",
                "object",
            ]
        )

    metadata = sanitize_metadata(
        {
            "source": "s" * 120,
            "duration_ms": 1_500,
            "gaze_ratio": 0.82,
            "visibility_state": True,
            "shortcut": float("inf"),
            "image": {
                "raw": "forbidden"
            },
        }
    )

    assert metadata == {
        "duration_ms": 1_500,
        "gaze_ratio": 0.82,
        "source": "s" * 100,
        "visibility_state": True,
    }


def test_service_records_same_type_again_after_cooldown(
    client,
    admin,
):
    exam = _exam(admin)

    submission = _active_submission(
        client,
        exam,
    )

    first_time = datetime(
        2026,
        8,
        18,
        10,
        0,
        tzinfo=UTC,
    )

    first, first_recorded = record_warning(
        submission,
        ViolationType.FACE_NOT_DETECTED,
        now=first_time,
    )

    second, second_recorded = record_warning(
        submission,
        ViolationType.FACE_NOT_DETECTED,
        now=(
            first_time
            + timedelta(seconds=4)
        ),
    )

    assert first_recorded is True
    assert second_recorded is True
    assert first.id != second.id
    assert second.metadata_json is None
    assert submission.warn_count == 2


def test_service_validation_and_limit_guards(
    client,
    admin,
):
    exam = _exam(admin)

    submission = _active_submission(
        client,
        exam,
    )

    assert violation_type_for_exam(
        "face_not_detected",
        MonitorType.FACE,
    ) is ViolationType.FACE_NOT_DETECTED

    with pytest.raises(
        InvalidViolationError
    ):
        violation_type_for_exam(
            None,
            MonitorType.FACE,
        )

    with pytest.raises(
        InvalidViolationError
    ):
        violation_type_for_exam(
            "not-real",
            MonitorType.FACE,
        )

    with pytest.raises(
        InvalidViolationError
    ):
        violation_type_for_exam(
            "gaze_deviation",
            MonitorType.FACE,
        )

    submission.warn_count = 3

    with pytest.raises(
        WarningLimitReachedError
    ):
        record_warning(
            submission,
            ViolationType.COPY_PASTE,
        )
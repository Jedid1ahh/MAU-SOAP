"""Tests for Phase 6 Candidate examination-session behavior."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.candidate.services import credential_digest
from app.candidate.session_services import (
    ExistingAttemptError,
    FinalizedSubmissionError,
    finalize_expired_submission,
    finalize_submission,
    finalize_warning_limit,
    remaining_seconds,
    resolve_submission_session,
    secrets_match,
    start_submission,
    submission_deadline,
)
from app.extensions import db
from app.models import (
    Exam,
    MonitorType,
    Question,
    QuestionType,
    ReleaseOption,
    Submission,
    VerificationToken,
)


def _exam(admin, *, token="phase-six-exam", with_questions=True):
    exam = Exam(
        admin_id=admin.id,
        title="Distributed Systems",
        course_code="CSC 406",
        course_title="Distributed Systems",
        instructions="Answer every question.",
        time_limit_minutes=30,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token=token,
    )
    db.session.add(exam)
    db.session.flush()

    if with_questions:
        db.session.add_all(
            [
                Question(
                    exam=exam,
                    question_text=(
                        "Which protocol provides reliable delivery?"
                    ),
                    question_type=QuestionType.MCQ,
                    position=1,
                    marks=Decimal("2.00"),
                    options={"A": "UDP", "B": "TCP"},
                    correct_answer="B",
                ),
                Question(
                    exam=exam,
                    question_text="Define consensus.",
                    question_type=QuestionType.SHORT_ANSWER,
                    position=2,
                    marks=Decimal("3.00"),
                    correct_answer="agreement",
                ),
                Question(
                    exam=exam,
                    question_text="Explain the CAP theorem.",
                    question_type=QuestionType.OPEN_ENDED,
                    position=3,
                    marks=Decimal("5.00"),
                    correct_answer=None,
                ),
            ]
        )

    db.session.commit()
    return exam


def _verified_access(
    client,
    exam,
    *,
    raw_token="candidate-session-token",
    name="Amina Bello",
    email="amina@gmail.com",
):
    now = datetime.now(UTC)

    verification = VerificationToken(
        exam=exam,
        candidate_name=name,
        candidate_email=email,
        otp_hash=credential_digest("123456"),
        magic_token_hash=credential_digest(
            f"magic-{raw_token}"
        ),
        session_token_hash=credential_digest(raw_token),
        verified_at=now,
        expires_at=now + timedelta(minutes=30),
    )

    db.session.add(verification)
    db.session.commit()

    with client.session_transaction() as candidate_session:
        candidate_session[
            f"candidate_access_token_{exam.id}"
        ] = raw_token

    return verification


def _started_submission(
    exam,
    *,
    raw_token="candidate-session-token",
    started_at=None,
    submitted_at=None,
):
    submission = Submission(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email="amina@gmail.com",
        responses={},
        resume_token_hash=credential_digest(raw_token),
        started_at=started_at or datetime.now(UTC),
        submitted_at=submitted_at,
        submission_reason=(
            "manual" if submitted_at else None
        ),
        warn_count=0,
    )

    db.session.add(submission)
    db.session.commit()

    return submission


def test_start_requires_verified_access_and_questions(
    client,
    admin,
):
    exam = _exam(admin)

    unauthorized = client.post(
        f"/exam/{exam.exam_link_token}/start"
    )

    assert unauthorized.status_code == 302
    assert unauthorized.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}"
    )

    assert db.session.scalar(
        select(Submission)
    ) is None


def test_start_requires_supervision_recording_consent(
    client,
    admin,
):
    exam = _exam(admin)
    _verified_access(client, exam)

    response = client.post(
        f"/exam/{exam.exam_link_token}/start"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/ready"
    )

    assert db.session.scalar(
        select(Submission)
    ) is None

    ready = client.get(
        response.headers["Location"]
    )

    assert b"Camera recording notice" in ready.data
    assert b"supervision_consent" in ready.data

    empty_exam = _exam(
        admin,
        token="empty-exam",
        with_questions=False,
    )

    _verified_access(
        client,
        empty_exam,
        raw_token="empty-token",
    )

    empty = client.post(
        f"/exam/{empty_exam.exam_link_token}/start"
    )

    assert empty.status_code == 302
    assert empty.headers["Location"].endswith(
        f"/exam/{empty_exam.exam_link_token}/ready"
    )

    assert db.session.scalar(
        select(Submission)
    ) is None


def test_start_creates_one_idempotent_attempt_and_locks_exam(
    client,
    admin,
):
    exam = _exam(admin)
    verification = _verified_access(client, exam)

    consent = {
        "supervision_consent": "yes",
    }

    first = client.post(
        f"/exam/{exam.exam_link_token}/start",
        data=consent,
    )

    second = client.post(
        f"/exam/{exam.exam_link_token}/start",
        data=consent,
    )

    submission = db.session.scalar(
        select(Submission)
    )

    assert first.status_code == 302
    assert first.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/session"
    )

    assert second.status_code == 302

    assert db.session.scalar(
        select(func.count(Submission.id))
    ) == 1

    assert (
        submission.candidate_name
        == verification.candidate_name
    )

    assert (
        submission.candidate_email
        == verification.candidate_email
    )

    assert submission.responses == {}
    assert submission.started_at is not None
    assert submission.submitted_at is None
    assert exam.is_locked is True

    page = client.get(
        f"/exam/{exam.exam_link_token}/session"
    )

    assert page.status_code == 200
    assert b"Examination in progress" in page.data
    assert b"Server synchronized" in page.data
    assert b"candidate-session-token" not in page.data


def test_different_verified_token_cannot_claim_existing_attempt(
    client,
    admin,
):
    exam = _exam(admin)

    _verified_access(
        client,
        exam,
        raw_token="first-token",
    )

    client.post(
        f"/exam/{exam.exam_link_token}/start",
        data={"supervision_consent": "yes"},
    )

    _verified_access(
        client,
        exam,
        raw_token="second-token",
    )

    response = client.post(
        f"/exam/{exam.exam_link_token}/start",
        data={"supervision_consent": "yes"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}"
    )

    assert db.session.scalar(
        select(func.count(Submission.id))
    ) == 1


def test_session_pages_require_matching_started_token(
    client,
    admin,
):
    exam = _exam(admin)

    session_page = client.get(
        f"/exam/{exam.exam_link_token}/session"
    )

    questions = client.get(
        f"/exam/{exam.exam_link_token}/session/questions"
    )

    timing = client.get(
        f"/exam/{exam.exam_link_token}/session/time"
    )

    receipt = client.get(
        f"/exam/{exam.exam_link_token}/submitted"
    )

    unknown = client.get(
        "/exam/not-a-real-token/session"
    )

    assert session_page.status_code == 302
    assert questions.status_code == 403

    assert questions.get_json() == {
        "error": "Candidate session required.",
    }

    assert timing.status_code == 403
    assert receipt.status_code == 302
    assert unknown.status_code == 404


def test_question_endpoint_never_exposes_grading_answers(
    client,
    admin,
):
    exam = _exam(admin)
    _verified_access(client, exam)

    client.post(
        f"/exam/{exam.exam_link_token}/start",
        data={"supervision_consent": "yes"},
    )

    response = client.get(
        f"/exam/{exam.exam_link_token}/session/questions"
    )

    payload = response.get_json()

    assert response.status_code == 200

    assert [
        item["question_type"]
        for item in payload["questions"]
    ] == [
        "mcq",
        "short_answer",
        "open_ended",
    ]

    assert payload["questions"][0]["options"] == {
        "A": "UDP",
        "B": "TCP",
    }

    assert "options" not in payload["questions"][1]
    assert "correct_answer" not in response.get_data(
        as_text=True
    )
    assert '"B"' in response.get_data(as_text=True)
    assert "agreement" not in response.get_data(
        as_text=True
    )


def test_server_time_endpoint_uses_started_at_not_browser_input(
    client,
    admin,
    monkeypatch,
):
    exam = _exam(admin)
    _verified_access(client, exam)

    started = datetime(
        2026,
        8,
        17,
        10,
        0,
        tzinfo=UTC,
    )

    now = started + timedelta(
        minutes=7,
        seconds=5,
    )

    submission = _started_submission(
        exam,
        started_at=started,
    )

    monkeypatch.setattr(
        "app.candidate.session_services.utc_now",
        lambda: now,
    )

    response = client.get(
        f"/exam/{exam.exam_link_token}/session/time"
    )

    payload = response.get_json()

    assert response.status_code == 200
    assert payload["remaining_seconds"] == 1_375
    assert (
        payload["deadline"]
        == "2026-08-17T10:30:00+00:00"
    )
    assert payload["submitted"] is False
    assert payload["reason"] is None
    assert submission.is_finalized is False


def test_expiry_finalizes_once_and_rejects_question_loading(
    client,
    admin,
    monkeypatch,
):
    exam = _exam(admin)
    _verified_access(client, exam)

    started = datetime(
        2026,
        8,
        17,
        10,
        0,
        tzinfo=UTC,
    )

    submission = _started_submission(
        exam,
        started_at=started,
    )

    monkeypatch.setattr(
        "app.candidate.session_services.utc_now",
        lambda: started + timedelta(minutes=31),
    )

    questions = client.get(
        f"/exam/{exam.exam_link_token}/session/questions"
    )

    session_page = client.get(
        f"/exam/{exam.exam_link_token}/session"
    )

    timing = client.get(
        f"/exam/{exam.exam_link_token}/session/time"
    )

    assert questions.status_code == 409

    assert questions.get_json() == {
        "reason": "time_expired",
        "submitted": True,
    }

    assert session_page.status_code == 302
    assert session_page.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/submitted"
    )

    assert timing.get_json()["remaining_seconds"] == 0
    assert submission.is_finalized is True
    assert (
        submission.submission_reason
        == "time_expired"
    )


def test_manual_submit_stores_only_known_responses_and_is_final(
    client,
    admin,
):
    exam = _exam(admin)
    _verified_access(client, exam)

    client.post(
        f"/exam/{exam.exam_link_token}/start",
        data={"supervision_consent": "yes"},
    )

    question_ids = [
        question.id
        for question in exam.questions
    ]

    response = client.post(
        f"/exam/{exam.exam_link_token}/session/submit",
        data={
            f"question_{question_ids[0]}": "B",
            f"question_{question_ids[1]}": (
                "Agreement by distributed nodes"
            ),
            f"question_{question_ids[2]}": (
                "CAP limits simultaneous guarantees."
            ),
            "question_999999": "must be ignored",
        },
    )

    submission = db.session.scalar(
        select(Submission)
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/submitted"
    )

    assert submission.responses == {
        str(question_ids[0]): "B",
        str(question_ids[1]): (
            "Agreement by distributed nodes"
        ),
        str(question_ids[2]): (
            "CAP limits simultaneous guarantees."
        ),
    }

    assert (
        submission.last_saved_at
        == submission.submitted_at
    )

    assert submission.submission_reason == "manual"

    receipt = client.get(
        response.headers["Location"]
    )

    second_write = client.post(
        f"/exam/{exam.exam_link_token}/session/submit",
        data={
            f"question_{question_ids[0]}": "A",
        },
    )

    questions = client.get(
        f"/exam/{exam.exam_link_token}/session/questions"
    )

    assert receipt.status_code == 200
    assert b"Submission received" in receipt.data
    assert b"Manual" in receipt.data

    assert (
        b"Grading and result release will be activated"
        in receipt.data
    )

    assert second_write.status_code == 409

    assert (
        submission.responses[str(question_ids[0])]
        == "B"
    )

    assert questions.status_code == 409


@pytest.mark.parametrize(
    "answer",
    [
        "not-an-option",
        "x" * 10_001,
    ],
)
def test_submit_rejects_invalid_answer_payload(
    client,
    admin,
    answer,
):
    exam = _exam(admin)
    _verified_access(client, exam)

    client.post(
        f"/exam/{exam.exam_link_token}/start",
        data={"supervision_consent": "yes"},
    )

    mcq_id = exam.questions[0].id

    response = client.post(
        f"/exam/{exam.exam_link_token}/session/submit",
        data={
            f"question_{mcq_id}": answer,
        },
    )

    submission = db.session.scalar(
        select(Submission)
    )

    assert response.status_code == 400
    assert submission.is_finalized is False
    assert submission.responses == {}


def test_submit_requires_started_session(
    client,
    admin,
):
    exam = _exam(admin)

    response = client.post(
        f"/exam/{exam.exam_link_token}/session/submit"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}"
    )


def test_expired_manual_payload_is_not_accepted(
    client,
    admin,
    monkeypatch,
):
    exam = _exam(admin)
    _verified_access(client, exam)

    started = datetime(
        2026,
        8,
        17,
        10,
        0,
        tzinfo=UTC,
    )

    submission = _started_submission(
        exam,
        started_at=started,
    )

    monkeypatch.setattr(
        "app.candidate.session_services.utc_now",
        lambda: started + timedelta(minutes=30),
    )

    response = client.post(
        f"/exam/{exam.exam_link_token}/session/submit",
        data={
            f"question_{exam.questions[0].id}": "B",
        },
    )

    assert response.status_code == 409
    assert submission.responses == {}

    assert (
        submission.submission_reason
        == "time_expired"
    )


def test_start_of_finalized_matching_attempt_opens_receipt(
    client,
    admin,
):
    exam = _exam(admin)
    verification = _verified_access(client, exam)

    submitted_at = datetime.now(UTC)

    _started_submission(
        exam,
        started_at=(
            submitted_at - timedelta(minutes=1)
        ),
        submitted_at=submitted_at,
    )

    response = client.post(
        f"/exam/{exam.exam_link_token}/start",
        data={"supervision_consent": "yes"},
    )

    assert (
        verification.candidate_email
        == "amina@gmail.com"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/submitted"
    )


def test_session_service_guards_and_rounding(
    app,
    admin,
    monkeypatch,
):
    exam = _exam(admin)

    started = datetime(
        2026,
        8,
        17,
        10,
        0,
        tzinfo=UTC,
    )

    submission = _started_submission(
        exam,
        started_at=started,
    )

    assert (
        resolve_submission_session(exam, None)
        is None
    )

    assert (
        resolve_submission_session(
            exam,
            "wrong-token",
        )
        is None
    )

    assert secrets_match("same", "same") is True

    assert (
        secrets_match("same", "different")
        is False
    )

    assert submission_deadline(
        submission
    ) == started + timedelta(minutes=30)

    assert remaining_seconds(
        submission,
        now=started + timedelta(
            microseconds=1
        ),
    ) == 1_800

    monkeypatch.setattr(
        "app.candidate.session_services.utc_now",
        lambda: started + timedelta(minutes=1),
    )

    assert (
        finalize_expired_submission(submission)
        is False
    )

    finalized_at = started + timedelta(minutes=1)
    submission.submitted_at = finalized_at

    assert (
        finalize_expired_submission(submission)
        is True
    )

    with pytest.raises(
        FinalizedSubmissionError
    ):
        finalize_submission(
            submission,
            {"1": "answer"},
        )


def test_warning_limit_service_finalizes_active_and_expired_attempts(
    admin,
):
    active_exam = _exam(
        admin,
        token="warning-limit-active",
    )
    active = _started_submission(active_exam)

    finalize_warning_limit(
        active,
        {"1": "saved answer"},
    )

    assert active.responses == {
        "1": "saved answer",
    }
    assert (
        active.last_saved_at ==
        active.submitted_at
    )
    assert (
        active.submission_reason ==
        "warning_limit"
    )

    finalize_warning_limit(active, {})

    assert active.responses == {
        "1": "saved answer",
    }

    expired_exam = _exam(
        admin,
        token="warning-limit-expired",
    )
    expired = _started_submission(
        expired_exam,
        raw_token="expired-warning-token",
        started_at=(
            datetime.now(UTC) -
            timedelta(minutes=31)
        ),
    )

    finalize_warning_limit(
        expired,
        {"1": "too late"},
    )

    assert (
        expired.submission_reason ==
        "time_expired"
    )

def test_start_service_recovers_matching_concurrent_insert(
    app,
    admin,
    monkeypatch,
):
    exam = _exam(admin)
    raw_token = "race-token"

    verification = VerificationToken(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email="amina@gmail.com",
        otp_hash=credential_digest("123456"),
        magic_token_hash=credential_digest(
            "magic-race"
        ),
        session_token_hash=credential_digest(
            raw_token
        ),
        verified_at=datetime.now(UTC),
        expires_at=(
            datetime.now(UTC)
            + timedelta(minutes=30)
        ),
    )

    concurrent = Submission(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email="amina@gmail.com",
        responses={},
        resume_token_hash=credential_digest(
            raw_token
        ),
        started_at=datetime.now(UTC),
        warn_count=0,
    )

    db.session.add_all(
        [
            verification,
            concurrent,
        ]
    )

    db.session.commit()

    original_scalar = db.session.scalar
    calls = 0

    def hide_first_query(statement):
        nonlocal calls

        calls += 1

        if calls == 1:
            return None

        return original_scalar(statement)

    monkeypatch.setattr(
        db.session,
        "scalar",
        hide_first_query,
    )

    resolved, created = start_submission(
        exam,
        verification,
        raw_token,
    )

    assert resolved.id == concurrent.id
    assert created is False


def test_start_service_rejects_unresolved_concurrent_insert(
    app,
    admin,
    monkeypatch,
):
    exam = _exam(admin)

    verification = VerificationToken(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email="amina@gmail.com",
        otp_hash=credential_digest("123456"),
        magic_token_hash=credential_digest(
            "magic-missing"
        ),
        session_token_hash=credential_digest(
            "missing-race-token"
        ),
        verified_at=datetime.now(UTC),
        expires_at=(
            datetime.now(UTC)
            + timedelta(minutes=30)
        ),
    )

    db.session.add(verification)
    db.session.commit()

    monkeypatch.setattr(
        db.session,
        "scalar",
        lambda _statement: None,
    )

    monkeypatch.setattr(
        db.session,
        "flush",
        lambda: (
            _ for _ in ()
        ).throw(
            IntegrityError(
                "INSERT",
                {},
                Exception("duplicate"),
            )
        ),
    )

    with pytest.raises(
        ExistingAttemptError
    ):
        start_submission(
            exam,
            verification,
            "missing-race-token",
        )
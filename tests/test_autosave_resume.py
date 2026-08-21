"""Tests for Phase 8 Candidate autosave and crash-safe resume."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.candidate.services import credential_digest
from app.candidate.session_services import (
    FinalizedSubmissionError,
    save_submission_progress,
)
from app.extensions import db
from app.models import (
    Exam,
    MonitorType,
    Question,
    QuestionType,
    ReleaseOption,
    Submission,
)


def _exam(admin, *, token="autosave-exam"):
    exam = Exam(
        admin_id=admin.id,
        title="Cloud Computing",
        course_code="CSC 410",
        course_title="Cloud Computing",
        time_limit_minutes=30,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token=token,
    )
    db.session.add(exam)
    db.session.flush()
    db.session.add_all(
        [
            Question(
                exam=exam,
                question_text="Which model provides virtual machines?",
                question_type=QuestionType.MCQ,
                position=1,
                marks=Decimal("2.00"),
                options={"A": "IaaS", "B": "SaaS"},
                correct_answer="A",
            ),
            Question(
                exam=exam,
                question_text="Define elasticity.",
                question_type=QuestionType.SHORT_ANSWER,
                position=2,
                marks=Decimal("3.00"),
                correct_answer="scaling",
            ),
        ]
    )
    db.session.commit()
    return exam


def _submission(
    client,
    exam,
    *,
    raw_token="phase-eight-resume-token",
    started_at=None,
    submitted_at=None,
    responses=None,
    warn_count=0,
):
    submission = Submission(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email="amina@gmail.com",
        responses=responses or {},
        resume_token_hash=credential_digest(raw_token),
        started_at=(
            started_at
            or (
                submitted_at - timedelta(minutes=1)
                if submitted_at is not None
                else datetime.now(UTC)
            )
        ),
        last_saved_at=None,
        submitted_at=submitted_at,
        submission_reason="manual" if submitted_at else None,
        warn_count=warn_count,
    )
    db.session.add(submission)
    db.session.commit()

    if client is not None:
        with client.session_transaction() as candidate_session:
            candidate_session[
                f"candidate_access_token_{exam.id}"
            ] = raw_token

    return submission


def _autosave_url(exam):
    return f"/exam/{exam.exam_link_token}/session/autosave"


def _answers(exam, *, mcq="A", short="Elastic scaling"):
    return {
        str(exam.questions[0].id): mcq,
        str(exam.questions[1].id): short,
    }


def test_session_bootstrap_restores_saved_answers_and_resume_credential(
    client,
    admin,
):
    exam = _exam(admin)
    saved_at = datetime.now(UTC)
    submission = _submission(
        client,
        exam,
        responses=_answers(exam),
        warn_count=2,
    )
    submission.last_saved_at = saved_at
    db.session.commit()

    page = client.get(f"/exam/{exam.exam_link_token}/session")
    questions = client.get(
        f"/exam/{exam.exam_link_token}/session/questions"
    )
    payload = questions.get_json()

    assert page.status_code == 200
    assert b"Answers save automatically" in page.data
    assert b"exam_autosave.js" in page.data
    assert b"phase-eight-resume-token" not in page.data
    assert questions.status_code == 200
    assert payload["responses"] == _answers(exam)
    assert payload["warning_count"] == 2
    assert payload["resume_token"] == "phase-eight-resume-token"
    assert payload["last_saved_at"] == saved_at.isoformat()


def test_autosave_persists_validated_progress_without_finalizing(
    client,
    admin,
):
    exam = _exam(admin)
    submission = _submission(client, exam, warn_count=1)
    answers = _answers(exam)

    response = client.post(
        _autosave_url(exam),
        json={
            "responses": {
                **answers,
                "999999": "ignored",
            }
        },
    )

    assert response.status_code == 200
    assert response.get_json()["saved"] is True
    assert response.get_json()["warning_count"] == 1
    assert response.get_json()["last_saved_at"]
    assert submission.responses == answers
    assert submission.last_saved_at is not None
    assert submission.submitted_at is None
    assert submission.submission_reason is None


@pytest.mark.parametrize(
    "payload,error",
    [
        ([], "A JSON autosave snapshot is required."),
        ({}, "Invalid autosave responses."),
        ({"responses": None}, "Invalid autosave responses."),
        ({"responses": []}, "Invalid autosave responses."),
        (
            {"responses": {"QUESTION_ID": 7}},
            "Invalid autosave responses.",
        ),
        (
            {"responses": {"QUESTION_ID": "x" * 10_001}},
            "Invalid autosave responses.",
        ),
        (
            {"responses": {"QUESTION_ID": "Z"}},
            "Invalid autosave responses.",
        ),
    ],
)
def test_autosave_rejects_malformed_or_untrusted_snapshots(
    client,
    admin,
    payload,
    error,
):
    exam = _exam(admin)
    submission = _submission(client, exam)

    if (
        isinstance(payload, dict)
        and isinstance(payload.get("responses"), dict)
    ):
        payload["responses"] = {
            (
                str(exam.questions[0].id)
                if key == "QUESTION_ID"
                else key
            ): value
            for key, value in payload["responses"].items()
        }

    response = client.post(_autosave_url(exam), json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"error": error}
    assert submission.responses == {}
    assert submission.last_saved_at is None


def test_autosave_requires_matching_candidate_session(
    client,
    admin,
):
    exam = _exam(admin)
    _submission(None, exam)

    response = client.post(
        _autosave_url(exam),
        json={"responses": _answers(exam)},
    )

    assert response.status_code == 403
    assert response.get_json() == {
        "error": "Candidate session required."
    }


def test_autosave_rejects_finalized_and_expired_attempts(
    client,
    admin,
):
    exam = _exam(admin)
    finalized_at = datetime.now(UTC)
    finalized = _submission(
        client,
        exam,
        submitted_at=finalized_at,
    )

    finalized_response = client.post(
        _autosave_url(exam),
        json={"responses": _answers(exam)},
    )

    assert finalized_response.status_code == 409
    assert finalized_response.get_json() == {
        "reason": "manual",
        "submitted": True,
    }
    assert finalized.responses == {}

    other_exam = _exam(
        admin,
        token="expired-autosave-exam",
    )
    expired = _submission(
        client,
        other_exam,
        raw_token="expired-phase-eight-token",
        started_at=datetime.now(UTC) - timedelta(minutes=31),
    )
    expired_response = client.post(
        _autosave_url(other_exam),
        json={"responses": _answers(other_exam)},
    )

    assert expired_response.status_code == 409
    assert expired_response.get_json() == {
        "reason": "time_expired",
        "submitted": True,
    }
    assert expired.responses == {}
    assert expired.submitted_at is not None


def test_resume_endpoint_restores_active_attempt_in_fresh_browser(
    app,
    admin,
):
    exam = _exam(admin)
    _submission(None, exam)
    fresh_client = app.test_client()

    response = fresh_client.post(
        f"/exam/{exam.exam_link_token}/resume",
        json={"resume_token": "phase-eight-resume-token"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "reason": None,
        "redirect_url": (
            f"/exam/{exam.exam_link_token}/session"
        ),
        "resumed": True,
        "submitted": False,
    }

    with fresh_client.session_transaction() as candidate_session:
        assert candidate_session[
            f"candidate_access_token_{exam.id}"
        ] == "phase-eight-resume-token"
        assert candidate_session.permanent is False

    session_page = fresh_client.get(
        f"/exam/{exam.exam_link_token}/session"
    )
    assert session_page.status_code == 200


@pytest.mark.parametrize(
    "payload,expected_status,expected_error",
    [
        (
            [],
            400,
            "A JSON resume request is required.",
        ),
        ({}, 400, "Invalid resume token."),
        (
            {"resume_token": 7},
            400,
            "Invalid resume token.",
        ),
        (
            {"resume_token": "short"},
            400,
            "Invalid resume token.",
        ),
        (
            {"resume_token": "x" * 256},
            400,
            "Invalid resume token.",
        ),
        (
            {
                "resume_token": (
                    "unknown-but-long-resume-token"
                )
            },
            404,
            "Saved examination attempt not found.",
        ),
    ],
)
def test_resume_endpoint_rejects_invalid_or_unknown_tokens(
    client,
    admin,
    payload,
    expected_status,
    expected_error,
):
    exam = _exam(admin)

    response = client.post(
        f"/exam/{exam.exam_link_token}/resume",
        json=payload,
    )

    assert response.status_code == expected_status
    assert response.get_json() == {
        "error": expected_error
    }


@pytest.mark.parametrize("state", ["finalized", "expired"])
def test_resume_endpoint_opens_receipt_for_closed_attempts(
    app,
    admin,
    state,
):
    exam = _exam(
        admin,
        token=f"{state}-resume-exam",
    )
    now = datetime.now(UTC)
    submission = _submission(
        None,
        exam,
        raw_token=f"{state}-phase-eight-token",
        started_at=(
            now - timedelta(minutes=31)
            if state == "expired"
            else now - timedelta(minutes=1)
        ),
        submitted_at=(
            now if state == "finalized" else None
        ),
    )
    fresh_client = app.test_client()

    response = fresh_client.post(
        f"/exam/{exam.exam_link_token}/resume",
        json={
            "resume_token": (
                f"{state}-phase-eight-token"
            )
        },
    )

    assert response.status_code == 200
    assert response.get_json()["redirect_url"] == (
        f"/exam/{exam.exam_link_token}/submitted"
    )
    assert response.get_json()["submitted"] is True
    assert submission.is_finalized is True
    assert submission.submission_reason == (
        "time_expired"
        if state == "expired"
        else "manual"
    )


@pytest.mark.parametrize(
    "state",
    ["active", "finalized", "expired"],
)
def test_landing_redirects_cookie_authenticated_attempts(
    client,
    admin,
    state,
):
    exam = _exam(
        admin,
        token=f"landing-{state}",
    )
    now = datetime.now(UTC)
    submission = _submission(
        client,
        exam,
        raw_token=f"landing-{state}-resume-token",
        started_at=(
            now - timedelta(minutes=31)
            if state == "expired"
            else now
        ),
        submitted_at=(
            now if state == "finalized" else None
        ),
    )

    response = client.get(
        f"/exam/{exam.exam_link_token}"
    )

    assert response.status_code == 302
    expected_suffix = (
        "submitted"
        if state != "active"
        else "session"
    )
    assert response.headers["Location"].endswith(
        
            f"/exam/{exam.exam_link_token}/"
            f"{expected_suffix}"
        
    )

    if state == "expired":
        assert (
            submission.submission_reason
            == "time_expired"
        )


def test_landing_and_receipt_include_browser_recovery_controls(
    client,
    admin,
):
    exam = _exam(admin)
    landing = client.get(
        f"/exam/{exam.exam_link_token}"
    )

    assert landing.status_code == 200
    assert b"candidate-entry" in landing.data
    assert b"candidate_resume.js" in landing.data
    assert (
        b"A saved examination attempt was found"
        in landing.data
    )

    resume_script = client.get(
        "/static/js/candidate_resume.js"
    )
    autosave_script = client.get(
        "/static/js/exam_autosave.js"
    )

    assert resume_script.status_code == 200
    assert (
        b"window.localStorage"
        in resume_script.data
    )
    assert b"resume_token" in resume_script.data
    assert autosave_script.status_code == 200
    assert (
        b"AUTOSAVE_INTERVAL_MS"
        in autosave_script.data
    )
    assert b"keepalive" in autosave_script.data
    assert b"mau-soap:draft" in autosave_script.data

    _submission(client, exam)
    submission = db.session.scalar(
        select(Submission)
    )
    submission.submitted_at = datetime.now(UTC)
    submission.submission_reason = "manual"
    db.session.commit()

    receipt = client.get(
        f"/exam/{exam.exam_link_token}/submitted"
    )

    assert receipt.status_code == 200
    assert b"mau-soap:draft:" in receipt.data


def test_autosave_service_rejects_direct_write_after_finalization(
    client,
    admin,
):
    exam = _exam(admin)
    submission = _submission(client, exam)

    save_submission_progress(
        submission,
        _answers(exam),
    )

    assert submission.responses == _answers(exam)
    assert submission.last_saved_at is not None

    submission.submitted_at = datetime.now(UTC)
    submission.submission_reason = "manual"

    with pytest.raises(FinalizedSubmissionError):
        save_submission_progress(submission, {})

    assert submission.responses == _answers(exam)
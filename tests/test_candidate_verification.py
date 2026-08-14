"""Tests for Phase 5 Candidate verification."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, select

from app.candidate.services import (
    aware_utc,
    complete_verification,
    create_verification,
    credential_digest,
    register_failed_attempt,
    resolve_candidate_session,
    send_verification_email,
    verification_is_expired,
)
from app.extensions import db, mail
from app.models import (
    Exam,
    MonitorType,
    ReleaseOption,
    Submission,
    VerificationToken,
)


def _exam(
    admin,
    *,
    token="candidate-exam-token",
    title="Database Systems",
):
    exam = Exam(
        admin_id=admin.id,
        title=title,
        course_code="CSC 402",
        course_title="Enterprise Database Management",
        instructions="Read every question carefully.",
        time_limit_minutes=45,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token=token,
    )

    db.session.add(exam)
    db.session.commit()

    return exam


def _request_verification(
    client,
    exam,
    *,
    name="Amina Bello",
    email="AMINA@GMAIL.COM",
):
    with mail.record_messages() as outbox:
        response = client.post(
            f"/exam/{exam.exam_link_token}",
            data={
                "name": name,
                "email": email,
            },
        )
        messages = list(outbox)

    return response, messages


def _email_credentials(message):
    otp_match = re.search(
        r"\b(\d{6})\b",
        message.body,
    )
    link_match = re.search(
        r"https?://[^\s]+",
        message.body,
    )

    assert otp_match is not None
    assert link_match is not None

    return (
        otp_match.group(1),
        urlsplit(link_match.group(0)).path,
    )


def _verification(exam, **overrides):
    values = {
        "exam": exam,
        "candidate_name": "Amina Bello",
        "candidate_email": "amina@gmail.com",
        "otp_hash": credential_digest("123456"),
        "magic_token_hash": credential_digest(
            "magic-token"
        ),
        "expires_at": (
            datetime.now(UTC)
            + timedelta(minutes=10)
        ),
    }
    values.update(overrides)

    verification = VerificationToken(**values)

    db.session.add(verification)
    db.session.commit()

    return verification


def _set_pending(
    client,
    exam,
    verification_id,
):
    with client.session_transaction() as candidate_session:
        candidate_session[
            f"candidate_pending_verification_{exam.id}"
        ] = verification_id


def test_candidate_landing_validates_identity_and_domain(
    client,
    admin,
):
    exam = _exam(admin)

    page = client.get(
        f"/exam/{exam.exam_link_token}"
    )

    invalid = client.post(
        f"/exam/{exam.exam_link_token}",
        data={
            "name": "",
            "email": "not-an-email",
        },
    )

    wrong_domain = client.post(
        f"/exam/{exam.exam_link_token}",
        data={
            "name": "Amina Bello",
            "email": "amina@mau.edu.ng",
        },
    )

    assert page.status_code == 200
    assert b"Verify your identity" in page.data
    assert b"Full name" in page.data

    assert invalid.status_code == 200
    assert b"This field is required" in invalid.data
    assert b"Invalid email address" in invalid.data

    assert wrong_domain.status_code == 200
    assert b"ending in @gmail.com" in wrong_domain.data


def test_request_sends_hashed_otp_and_magic_link(
    client,
    admin,
):
    exam = _exam(admin)

    response, messages = _request_verification(
        client,
        exam,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/verify"
    )

    assert len(messages) == 1
    assert messages[0].recipients == [
        "amina@gmail.com"
    ]
    assert "Database Systems" in messages[0].subject

    raw_otp, magic_path = _email_credentials(
        messages[0]
    )

    verification = db.session.scalar(
        select(VerificationToken)
    )

    assert verification is not None
    assert verification.candidate_name == "Amina Bello"
    assert (
        verification.candidate_email
        == "amina@gmail.com"
    )
    assert verification.otp_hash == credential_digest(
        raw_otp
    )
    assert verification.magic_token_hash != (
        magic_path.rsplit("/", 1)[-1]
    )
    assert raw_otp not in verification.otp_hash
    assert verification.attempts == 0
    assert verification.verified_at is None
    assert verification.session_token_hash is None

    assert (
        db.session.scalar(
            select(func.count(Submission.id))
        )
        == 0
    )

    verify_page = client.get(
        f"/exam/{exam.exam_link_token}/verify"
    )

    assert verify_page.status_code == 200
    assert b"Check your email" in verify_page.data

    with client.session_transaction() as candidate_session:
        assert candidate_session[
            f"candidate_pending_verification_{exam.id}"
        ] == verification.id


def test_token_generation_uses_csprng_sizes(
    app,
    admin,
    monkeypatch,
):
    exam = _exam(admin)
    calls = []

    monkeypatch.setattr(
        "app.candidate.services.secrets.randbelow",
        lambda upper_bound: (
            calls.append(("otp", upper_bound))
            or 42
        ),
    )

    monkeypatch.setattr(
        "app.candidate.services.secrets.token_urlsafe",
        lambda byte_count: (
            calls.append(("token", byte_count))
            or "random-token"
        ),
    )

    raw_otp, raw_magic, verification = (
        create_verification(
            exam,
            " Candidate Name ",
            " CANDIDATE@GMAIL.COM ",
        )
    )

    raw_session = complete_verification(
        verification
    )

    assert raw_otp == "000042"
    assert raw_magic == "random-token"
    assert raw_session == "random-token"

    assert calls == [
        ("otp", 1_000_000),
        ("token", 32),
        ("token", 32),
    ]

    assert (
        verification.candidate_name
        == "Candidate Name"
    )
    assert (
        verification.candidate_email
        == "candidate@gmail.com"
    )


def test_requesting_new_code_locks_previous_token(
    client,
    admin,
):
    exam = _exam(admin)

    _request_verification(client, exam)

    _request_verification(
        client,
        exam,
        name="Amina Updated",
    )

    tokens = db.session.scalars(
        select(VerificationToken).order_by(
            VerificationToken.id
        )
    ).all()

    assert len(tokens) == 2
    assert tokens[0].is_locked is True
    assert tokens[1].is_locked is False
    assert (
        tokens[1].candidate_name
        == "Amina Updated"
    )


def test_email_failure_rolls_back_verification(
    client,
    admin,
    monkeypatch,
):
    exam = _exam(admin)

    def fail_delivery(*_args):
        raise RuntimeError("SMTP unavailable")

    monkeypatch.setattr(
        (
            "app.candidate.routes."
            "send_verification_email"
        ),
        fail_delivery,
    )

    response = client.post(
        f"/exam/{exam.exam_link_token}",
        data={
            "name": "Amina Bello",
            "email": "amina@gmail.com",
        },
    )

    assert response.status_code == 200
    assert b"Verification email could not be sent" in (
        response.data
    )
    assert db.session.scalar(
        select(VerificationToken)
    ) is None


def test_email_service_sends_when_enabled(
    app,
    admin,
    monkeypatch,
):
    exam = _exam(admin)
    verification = _verification(exam)
    sent_messages = []

    app.config["MAIL_SUPPRESS_SEND"] = False

    monkeypatch.setattr(
        mail,
        "send",
        sent_messages.append,
    )

    with app.test_request_context():
        send_verification_email(
            verification,
            "123456",
            "magic-token",
        )

    assert len(sent_messages) == 1
    assert sent_messages[0].recipients == [
        "amina@gmail.com"
    ]
    assert "123456" in sent_messages[0].body


def test_otp_page_requires_pending_request(
    client,
    admin,
):
    exam = _exam(admin)

    response = client.get(
        f"/exam/{exam.exam_link_token}/verify"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}"
    )

    _set_pending(client, exam, 99999)

    assert client.get(
        f"/exam/{exam.exam_link_token}/verify"
    ).status_code == 302


def test_wrong_otps_lock_after_five_failures(
    client,
    admin,
):
    exam = _exam(admin)

    _, messages = _request_verification(
        client,
        exam,
    )

    raw_otp, _ = _email_credentials(messages[0])

    wrong_otp = (
        "999999"
        if raw_otp != "999999"
        else "000000"
    )

    verification = db.session.scalar(
        select(VerificationToken)
    )

    verify_url = (
        f"/exam/{exam.exam_link_token}/verify"
    )

    malformed = client.post(
        verify_url,
        data={"otp": "abc"},
    )

    assert malformed.status_code == 200
    assert b"Enter the six-digit code" in malformed.data
    assert b"4 attempt(s) remaining" in malformed.data

    for expected_attempt in range(2, 6):
        response = client.post(
            verify_url,
            data={"otp": wrong_otp},
        )

        if expected_attempt < 5:
            assert response.status_code == 200
            assert (
                f"{5 - expected_attempt} attempt(s) "
                f"remaining"
            ).encode() in response.data
        else:
            assert response.status_code == 302

    assert verification.attempts == 5
    assert verification.locked_at is not None
    assert verification.is_locked is True

    assert client.get(
        verify_url
    ).status_code == 302


def test_expired_and_used_pending_requests_rejected(
    client,
    admin,
):
    exam = _exam(admin)

    verify_url = (
        f"/exam/{exam.exam_link_token}/verify"
    )

    expired = _verification(
        exam,
        expires_at=(
            datetime.now(UTC)
            - timedelta(seconds=1)
        ),
    )

    _set_pending(client, exam, expired.id)

    assert client.get(
        verify_url
    ).status_code == 302

    verified = _verification(
        exam,
        magic_token_hash=credential_digest(
            "second-magic"
        ),
        verified_at=datetime.now(UTC),
    )

    _set_pending(client, exam, verified.id)

    assert client.get(
        verify_url
    ).status_code == 302


def test_correct_otp_issues_protected_access(
    client,
    admin,
):
    exam = _exam(admin)

    _, messages = _request_verification(
        client,
        exam,
    )

    raw_otp, _ = _email_credentials(messages[0])

    verification = db.session.scalar(
        select(VerificationToken)
    )

    response = client.post(
        f"/exam/{exam.exam_link_token}/verify",
        data={"otp": raw_otp},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/ready"
    )

    assert verification.verified_at is not None
    assert verification.session_token_hash is not None
    assert db.session.scalar(
        select(Submission)
    ) is None
    assert exam.is_locked is False

    with client.session_transaction() as candidate_session:
        raw_session_token = candidate_session[
            f"candidate_access_token_{exam.id}"
        ]

        assert (
            f"candidate_pending_verification_{exam.id}"
            not in candidate_session
        )
        assert candidate_session.permanent is True

    assert verification.session_token_hash == (
        credential_digest(raw_session_token)
    )

    ready = client.get(
        f"/exam/{exam.exam_link_token}/ready"
    )

    assert ready.status_code == 200
    assert b"Email verified" in ready.data
    assert b"Amina Bello" in ready.data
    assert b"timer is" in ready.data
    assert b"not running" in ready.data
    assert b"Start examination" in ready.data

    landing = client.get(
        f"/exam/{exam.exam_link_token}"
    )

    assert landing.status_code == 302
    assert landing.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/ready"
    )


def test_valid_magic_link_works_in_fresh_browser(
    client,
    admin,
):
    exam = _exam(admin)

    _, messages = _request_verification(
        client,
        exam,
    )

    _, magic_path = _email_credentials(messages[0])

    verification = db.session.scalar(
        select(VerificationToken)
    )

    client.delete_cookie("session")

    response = client.get(magic_path)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/ready"
    )

    assert verification.verified_at is not None

    assert client.get(
        f"/exam/{exam.exam_link_token}/ready"
    ).status_code == 200


def test_invalid_magic_link_states_rejected(
    client,
    admin,
):
    exam = _exam(admin)

    other_exam = _exam(
        admin,
        token="other-exam-token",
        title="Other exam",
    )

    now = datetime.now(UTC)

    valid = _verification(exam)

    locked = _verification(
        exam,
        magic_token_hash=credential_digest(
            "locked-magic"
        ),
        locked_at=now,
    )

    used = _verification(
        exam,
        magic_token_hash=credential_digest(
            "used-magic"
        ),
        verified_at=now,
    )

    expired = _verification(
        exam,
        magic_token_hash=credential_digest(
            "expired-magic"
        ),
        expires_at=now - timedelta(seconds=1),
    )

    paths = [
        (
            f"/exam/{exam.exam_link_token}/"
            f"verify/unknown"
        ),
        (
            f"/exam/{other_exam.exam_link_token}/"
            f"verify/magic-token"
        ),
        (
            f"/exam/{exam.exam_link_token}/"
            f"verify/locked-magic"
        ),
        (
            f"/exam/{exam.exam_link_token}/"
            f"verify/used-magic"
        ),
        (
            f"/exam/{exam.exam_link_token}/"
            f"verify/expired-magic"
        ),
    ]

    for path in paths:
        response = client.get(path)

        assert response.status_code == 302

        landing = client.get(
            response.headers["Location"]
        )

        assert b"invalid or has expired" in (
            landing.data
        )

    assert valid.verified_at is None
    assert locked.is_locked is True
    assert used.verified_at is not None
    assert verification_is_expired(expired) is True


def test_ready_rejects_invalid_sessions(
    client,
    admin,
):
    exam = _exam(admin)

    ready_url = (
        f"/exam/{exam.exam_link_token}/ready"
    )

    assert client.get(
        ready_url
    ).status_code == 302

    with client.session_transaction() as candidate_session:
        candidate_session[
            f"candidate_access_token_{exam.id}"
        ] = "bad-token"

    assert client.get(
        ready_url
    ).status_code == 302

    verification = _verification(
        exam,
        session_token_hash=credential_digest(
            "expired-session"
        ),
        verified_at=datetime.now(UTC),
        expires_at=(
            datetime.now(UTC)
            - timedelta(seconds=1)
        ),
    )

    with client.session_transaction() as candidate_session:
        candidate_session[
            f"candidate_access_token_{exam.id}"
        ] = "expired-session"

    assert client.get(
        ready_url
    ).status_code == 302

    assert resolve_candidate_session(
        exam,
        None,
    ) is None

    assert verification_is_expired(
        verification
    ) is True


def test_completion_revokes_sibling_access(
    app,
    admin,
):
    exam = _exam(admin)

    sibling = _verification(
        exam,
        session_token_hash=credential_digest(
            "old-session"
        ),
        verified_at=datetime.now(UTC),
    )

    current = _verification(
        exam,
        magic_token_hash=credential_digest(
            "new-magic"
        ),
    )

    raw_session = complete_verification(current)

    register_failed_attempt(current)
    current.attempts = 5
    register_failed_attempt(current)

    assert sibling.is_locked is True
    assert current.session_token_hash == (
        credential_digest(raw_session)
    )
    assert current.attempts == 5
    assert current.is_locked is True


def test_timezone_normalizer_and_candidate_index(
    client,
):
    aware = datetime.now(UTC)
    naive = aware.replace(tzinfo=None)

    assert aware_utc(aware) == aware
    assert aware_utc(naive).tzinfo is UTC

    response = client.get("/exam/")

    assert response.status_code == 200
    assert b"secure examination link" in response.data
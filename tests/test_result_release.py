"""Tests for Phase 10 result release and secure Candidate result access."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.candidate.services import credential_digest
from app.extensions import db
from app.grading import assign_manual_grade, grade_submission
from app.models import (
    Exam,
    MonitorType,
    Question,
    QuestionType,
    ReleaseOption,
    ResultStatus,
    Submission,
)
from app.result_release import (
    ResultNotCompleteError,
    aware_utc,
    release_result_now,
    synchronize_result_release,
)


def _exam(
    admin,
    *,
    token="result-release-exam",
    release_option=ReleaseOption.IMMEDIATE,
    scheduled_release_at=None,
    include_open=False,
):
    exam = Exam(
        admin_id=admin.id,
        title="Computer Networks",
        course_code="CSC 430",
        course_title="Computer Networks",
        time_limit_minutes=30,
        monitor_type=MonitorType.FACE,
        release_option=release_option,
        scheduled_release_at=scheduled_release_at,
        exam_link_token=token,
    )
    db.session.add(exam)
    db.session.flush()

    questions = [
        Question(
            exam=exam,
            question_text=(
                "Which protocol is connection oriented?"
            ),
            question_type=QuestionType.MCQ,
            position=1,
            marks=Decimal("4.00"),
            options={
                "A": "TCP",
                "B": "UDP",
            },
            correct_answer="A",
        )
    ]

    if include_open:
        questions.append(
            Question(
                exam=exam,
                question_text="Explain congestion control.",
                question_type=QuestionType.OPEN_ENDED,
                position=2,
                marks=Decimal("6.00"),
            )
        )

    db.session.add_all(questions)
    db.session.commit()

    return exam


def _submission(
    exam,
    *,
    raw_token="candidate-result-session-token",
    email="candidate@gmail.com",
    finalized=True,
):
    responses = {
        str(exam.questions[0].id): "A",
    }

    if len(exam.questions) > 1:
        responses[str(exam.questions[1].id)] = (
            "Congestion control regulates network load."
        )

    submission = Submission(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email=email,
        responses=responses,
        resume_token_hash=credential_digest(raw_token),
        started_at=datetime.now(UTC),
        submitted_at=(
            datetime.now(UTC)
            if finalized
            else None
        ),
        submission_reason=(
            "manual"
            if finalized
            else None
        ),
    )

    db.session.add(submission)
    db.session.commit()

    return submission


def _candidate_session(
    client,
    exam,
    raw_token,
):
    with client.session_transaction() as candidate_session:
        candidate_session[
            f"candidate_access_token_{exam.id}"
        ] = raw_token


def _login(client):
    response = client.post(
        "/admin/login",
        data={
            "email": "admin@mau.edu.ng",
            "password": "Phase3TestPassword!",
        },
    )

    assert response.status_code == 302


def _exam_form_data(**overrides):
    data = {
        "title": "Release Policy Examination",
        "course_code": "CSC 440",
        "course_title": "Distributed Applications",
        "instructions": "Answer every question.",
        "time_limit_minutes": "45",
        "monitor_type": MonitorType.FACE.value,
        "release_option": ReleaseOption.IMMEDIATE.value,
        "scheduled_release_at": "",
    }
    data.update(overrides)

    return data


def test_aware_utc_normalizes_naive_and_aware_values():
    naive = datetime(
        2026,
        8,
        26,
        10,
        30,
    )
    aware = datetime(
        2026,
        8,
        26,
        11,
        30,
        tzinfo=UTC,
    )

    assert aware_utc(naive) == datetime(
        2026,
        8,
        26,
        10,
        30,
        tzinfo=UTC,
    )
    assert aware_utc(aware) is aware


def test_immediate_complete_result_releases_automatically(
    admin,
):
    exam = _exam(admin)
    submission = _submission(exam)

    result = grade_submission(submission)
    db.session.commit()

    assert result.status is ResultStatus.COMPLETE
    assert result.released_at is not None

    original_release = result.released_at

    assert synchronize_result_release(result) is True
    assert result.released_at == original_release


def test_incomplete_result_cannot_release_automatically_or_manually(
    admin,
):
    exam = _exam(
        admin,
        include_open=True,
    )
    submission = _submission(exam)
    result = grade_submission(submission)

    assert synchronize_result_release(result) is False
    assert result.released_at is None

    with pytest.raises(
        ResultNotCompleteError,
        match="Complete every",
    ):
        release_result_now(result)


def test_scheduled_result_releases_only_when_due(admin):
    release_time = datetime(
        2026,
        8,
        27,
        12,
        0,
        tzinfo=UTC,
    )

    exam = _exam(
        admin,
        release_option=ReleaseOption.SCHEDULED,
        scheduled_release_at=release_time,
    )
    submission = _submission(exam)
    result = grade_submission(submission)

    before = release_time - timedelta(seconds=1)

    assert (
        synchronize_result_release(
            result,
            now=before,
        )
        is False
    )
    assert result.released_at is None

    after = release_time + timedelta(seconds=1)

    assert (
        synchronize_result_release(
            result,
            now=after,
        )
        is True
    )
    assert result.released_at == after


def test_admin_manual_release_is_idempotent(admin):
    exam = _exam(
        admin,
        release_option=ReleaseOption.SCHEDULED,
        scheduled_release_at=(
            datetime.now(UTC) + timedelta(days=1)
        ),
    )
    submission = _submission(exam)
    result = grade_submission(submission)

    release_time = datetime(
        2026,
        8,
        26,
        15,
        0,
        tzinfo=UTC,
    )

    release_result_now(
        result,
        now=release_time,
    )
    release_result_now(
        result,
        now=release_time + timedelta(hours=1),
    )

    assert result.released_at == release_time


def test_candidate_result_requires_matching_finalized_session(
    client,
    admin,
):
    exam = _exam(admin)
    submission = _submission(
        exam,
        finalized=False,
    )

    unknown = client.get(
        "/exam/not-a-real-exam/result"
    )
    missing = client.get(
        f"/exam/{exam.exam_link_token}/result"
    )

    _candidate_session(
        client,
        exam,
        "wrong-session-token",
    )
    wrong = client.get(
        f"/exam/{exam.exam_link_token}/result"
    )

    _candidate_session(
        client,
        exam,
        "candidate-result-session-token",
    )
    active = client.get(
        f"/exam/{exam.exam_link_token}/result"
    )

    assert unknown.status_code == 404
    assert missing.status_code == 302
    assert wrong.status_code == 302
    assert active.status_code == 302
    assert active.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}"
    )
    assert submission.result is None


def test_candidate_sees_pending_manual_review_without_score(
    client,
    admin,
):
    exam = _exam(
        admin,
        include_open=True,
    )
    submission = _submission(exam)

    _candidate_session(
        client,
        exam,
        "candidate-result-session-token",
    )

    response = client.get(
        f"/exam/{exam.exam_link_token}/result"
    )

    assert response.status_code == 200
    assert b"Result pending" in response.data
    assert (
        b"open-ended responses still require Admin grading"
        in response.data
    )
    assert b"4.00 / 10.00" not in response.data
    assert submission.result.released_at is None


def test_candidate_sees_complete_scheduled_result_as_pending(
    client,
    admin,
):
    release_time = (
        datetime.now(UTC) + timedelta(days=1)
    )

    exam = _exam(
        admin,
        release_option=ReleaseOption.SCHEDULED,
        scheduled_release_at=release_time,
    )
    submission = _submission(exam)

    _candidate_session(
        client,
        exam,
        "candidate-result-session-token",
    )

    response = client.get(
        f"/exam/{exam.exam_link_token}/result"
    )

    assert response.status_code == 200
    assert b"Grading is complete" in response.data
    assert b"scheduled for release" in response.data
    assert b"4.00 / 4.00" not in response.data
    assert submission.result.released_at is None


def test_candidate_sees_released_breakdown_and_admin_feedback(
    client,
    admin,
):
    exam = _exam(
        admin,
        include_open=True,
    )
    submission = _submission(exam)

    grade_submission(submission)

    open_grade = next(
        grade
        for grade in submission.answer_grades
        if (
            grade.question.question_type
            is QuestionType.OPEN_ENDED
        )
    )

    assign_manual_grade(
        open_grade,
        Decimal("5.00"),
        admin,
        "Strong explanation.",
    )
    db.session.commit()

    _candidate_session(
        client,
        exam,
        "candidate-result-session-token",
    )

    response = client.get(
        f"/exam/{exam.exam_link_token}/result"
    )

    assert response.status_code == 200
    assert b"Result released" in response.data
    assert b"9.00 / 10.00" in response.data
    assert b"90.00%" in response.data
    assert (
        b"Congestion control regulates network load."
        in response.data
    )
    assert b"Strong explanation." in response.data
    assert b"correct_answer" not in response.data


def test_submission_receipt_links_to_secure_result(
    client,
    admin,
):
    exam = _exam(admin)
    _submission(exam)

    _candidate_session(
        client,
        exam,
        "candidate-result-session-token",
    )

    response = client.get(
        f"/exam/{exam.exam_link_token}/submitted"
    )

    assert response.status_code == 200
    assert b"Check result" in response.data
    assert (
        f"/exam/{exam.exam_link_token}/result".encode()
        in response.data
    )


def test_admin_results_routes_require_login(client):
    overview = client.get("/admin/results")
    release = client.post(
        "/admin/results/1/release"
    )

    assert overview.status_code == 302
    assert release.status_code == 302
    assert "/admin/login" in overview.headers["Location"]


def test_admin_results_empty_state_and_dashboard_link(
    client,
    admin,
):
    _login(client)

    dashboard = client.get("/admin/")
    overview = client.get("/admin/results")

    assert dashboard.status_code == 200
    assert b"Candidate results" in dashboard.data
    assert overview.status_code == 200
    assert b"No finalized submissions yet" in overview.data


def test_admin_results_overview_shows_released_pending_and_scheduled(
    client,
    admin,
):
    immediate_exam = _exam(
        admin,
        token="immediate-result",
    )
    immediate = _submission(
        immediate_exam,
        raw_token="released-result-session-token",
        email="released@gmail.com",
    )

    pending_exam = _exam(
        admin,
        token="pending-result",
        include_open=True,
    )
    pending = _submission(
        pending_exam,
        raw_token="pending-result-session-token",
        email="pending@gmail.com",
    )

    scheduled_exam = _exam(
        admin,
        token="scheduled-result",
        release_option=ReleaseOption.SCHEDULED,
        scheduled_release_at=(
            datetime.now(UTC) + timedelta(days=1)
        ),
    )
    scheduled = _submission(
        scheduled_exam,
        raw_token="scheduled-result-session-token",
        email="scheduled@gmail.com",
    )

    _login(client)

    response = client.get("/admin/results")

    assert response.status_code == 200
    assert b"released@gmail.com" in response.data
    assert b"pending@gmail.com" in response.data
    assert b"scheduled@gmail.com" in response.data
    assert b"Released" in response.data
    assert b"Pending grading" in response.data
    assert b"Awaiting release" in response.data
    assert b"Release now" in response.data
    assert immediate.result.released_at is not None
    assert pending.result.released_at is None
    assert scheduled.result.released_at is None


def test_admin_can_release_completed_scheduled_result(
    client,
    admin,
):
    exam = _exam(
        admin,
        release_option=ReleaseOption.SCHEDULED,
        scheduled_release_at=(
            datetime.now(UTC) + timedelta(days=1)
        ),
    )
    submission = _submission(exam)

    _login(client)

    response = client.post(
        f"/admin/results/{submission.id}/release"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/admin/results"
    )
    assert submission.result.released_at is not None

    overview = client.get("/admin/results")

    assert b"Candidate result released." in overview.data


def test_admin_cannot_release_pending_or_unknown_result(
    client,
    admin,
):
    pending_exam = _exam(
        admin,
        include_open=True,
    )
    pending = _submission(pending_exam)

    _login(client)

    pending_response = client.post(
        f"/admin/results/{pending.id}/release"
    )
    unknown = client.post(
        "/admin/results/999999/release"
    )

    assert pending_response.status_code == 302

    follow = client.get(
        pending_response.headers["Location"]
    )

    assert (
        b"Complete every pending manual grade"
        in follow.data
    )
    assert pending.result.released_at is None
    assert unknown.status_code == 404


def test_exam_form_configures_immediate_release(
    client,
    admin,
):
    _login(client)

    response = client.post(
        "/admin/exams/new",
        data=_exam_form_data(
            scheduled_release_at="2099-01-01T12:00",
        ),
    )

    assert response.status_code == 302

    exam = (
        db.session.query(Exam)
        .filter_by(course_code="CSC 440")
        .one()
    )

    assert (
        exam.release_option
        is ReleaseOption.IMMEDIATE
    )
    assert exam.scheduled_release_at is None


@pytest.mark.parametrize(
    "scheduled_release_at,expected_message",
    [
        (
            "",
            b"Choose when the result should be released",
        ),
        (
            "2020-01-01T12:00",
            b"Scheduled release must be in the future",
        ),
    ],
)
def test_exam_form_rejects_invalid_scheduled_release(
    client,
    admin,
    scheduled_release_at,
    expected_message,
):
    _login(client)

    response = client.post(
        "/admin/exams/new",
        data=_exam_form_data(
            release_option=ReleaseOption.SCHEDULED.value,
            scheduled_release_at=scheduled_release_at,
        ),
    )

    assert response.status_code == 200
    assert expected_message in response.data


def test_exam_form_saves_and_prefills_scheduled_release(
    client,
    admin,
):
    release_value = "2099-01-01T12:30"

    _login(client)

    created = client.post(
        "/admin/exams/new",
        data=_exam_form_data(
            release_option=ReleaseOption.SCHEDULED.value,
            scheduled_release_at=release_value,
        ),
    )

    exam = (
        db.session.query(Exam)
        .filter_by(course_code="CSC 440")
        .one()
    )

    edit_page = client.get(
        f"/admin/exams/{exam.id}/edit"
    )
    detail = client.get(
        f"/admin/exams/{exam.id}"
    )

    assert created.status_code == 302
    assert (
        exam.release_option
        is ReleaseOption.SCHEDULED
    )
    assert aware_utc(
        exam.scheduled_release_at
    ) == datetime(
        2099,
        1,
        1,
        12,
        30,
        tzinfo=UTC,
    )
    assert release_value.encode() in edit_page.data
    assert b"Scheduled" in detail.data
    assert b"2099-01-01" in detail.data
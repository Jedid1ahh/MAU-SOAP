"""Tests for logged-in, enrollment-gated Student examination access."""

from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Exam,
    MonitorType,
    Question,
    QuestionType,
    ReleaseOption,
    Submission,
)
from tests.helpers import authenticate_enrolled_student, course_for


def _exam(admin):
    exam = Exam(
        admin_id=admin.id,
        course=course_for(admin, "CIE 111", "Introduction to Computing"),
        title="Introduction to Computing",
        course_code="CIE 111",
        course_title="Introduction to Computing",
        time_limit_minutes=40,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token="authenticated-student-exam",
    )
    db.session.add(exam)
    db.session.flush()
    db.session.add(
        Question(
            exam=exam,
            question_text="What does CPU mean?",
            question_type=QuestionType.MCQ,
            position=1,
            marks=Decimal("2.00"),
            options={"A": "Central Processing Unit", "B": "Computer Power Unit"},
            correct_answer="A",
        )
    )
    db.session.commit()
    return exam


def test_exam_routes_require_a_logged_in_student(client, admin):
    exam = _exam(admin)

    landing = client.get(f"/exam/{exam.exam_link_token}")
    start = client.post(f"/exam/{exam.exam_link_token}/start")
    questions = client.get(f"/exam/{exam.exam_link_token}/session/questions")

    for response in (landing, start, questions):
        assert response.status_code == 302
        assert "/account/login" in response.headers["Location"]


def test_pending_or_missing_enrollment_cannot_open_exam(client, admin):
    exam = _exam(admin)
    authenticate_enrolled_student(client, exam, accepted=False)

    assert client.get(f"/exam/{exam.exam_link_token}").status_code == 403
    assert client.post(f"/exam/{exam.exam_link_token}/start").status_code == 403


def test_open_exam_starts_authenticated_student_directly(client, admin):
    exam = _exam(admin)
    student = authenticate_enrolled_student(client, exam)

    landing = client.get(f"/exam/{exam.exam_link_token}")
    assert landing.status_code == 302
    assert landing.headers["Location"].endswith("/student/")

    opened = client.post(f"/exam/{exam.exam_link_token}/start")
    assert opened.status_code == 302
    assert opened.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/session"
    )

    submission = db.session.scalar(select(Submission))
    assert submission is not None
    assert submission.candidate_name == student.full_name
    assert submission.candidate_email == student.email
    assert submission.supervision_consent_at == submission.started_at

    page = client.get(opened.headers["Location"])
    assert page.status_code == 200
    assert b"Verify your identity" not in page.data
    assert b"verification code" not in page.data


def test_old_exam_verification_links_return_to_student_dashboard(client, admin):
    exam = _exam(admin)
    authenticate_enrolled_student(client, exam)

    otp = client.get(f"/exam/{exam.exam_link_token}/verify")
    magic = client.get(f"/exam/{exam.exam_link_token}/verify/old-token")

    for response in (otp, magic):
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/student/")


def test_started_attempt_resumes_by_logged_in_account(client, admin):
    exam = _exam(admin)
    authenticate_enrolled_student(client, exam)
    client.post(f"/exam/{exam.exam_link_token}/start")

    reopened = client.post(f"/exam/{exam.exam_link_token}/start")
    resumed = client.post(f"/exam/{exam.exam_link_token}/resume", json={})

    assert reopened.headers["Location"].endswith(
        f"/exam/{exam.exam_link_token}/session"
    )
    assert resumed.status_code == 200
    assert resumed.get_json()["redirect_url"].endswith(
        f"/exam/{exam.exam_link_token}/session"
    )
    assert db.session.scalar(select(Submission)) is not None
    assert db.session.query(Submission).count() == 1

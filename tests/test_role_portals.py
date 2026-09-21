"""Tests for the initial Lecturer and Student dashboards."""

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.extensions import bcrypt, db
from app.grading import grade_submission
from app.models import (
    Exam,
    MonitorType,
    Question,
    QuestionType,
    ReleaseOption,
    Role,
    Submission,
    User,
)


def _account(email: str, role: Role) -> User:
    now = datetime.now(UTC)
    user = User(
        full_name="Portal User",
        email=email,
        password_hash=bcrypt.generate_password_hash(
            "InstitutionPassword!"
        ).decode("utf-8"),
        role=role,
        email_verified_at=now,
        approved_at=now,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user: User):
    return client.post(
        "/account/login",
        data={
            "email": user.email,
            "password": "InstitutionPassword!",
        },
    )


def _exam(owner: User, *, scheduled: bool = False) -> Exam:
    exam = Exam(
        admin=owner,
        title="Algorithms Examination",
        course_code="CSC 401",
        course_title="Algorithms",
        time_limit_minutes=45,
        monitor_type=MonitorType.FACE,
        release_option=(
            ReleaseOption.SCHEDULED if scheduled else ReleaseOption.IMMEDIATE
        ),
        scheduled_release_at=(
            datetime.now(UTC) + timedelta(days=1) if scheduled else None
        ),
        exam_link_token=secrets.token_urlsafe(32),
    )
    exam.questions.append(
        Question(
            position=1,
            question_text="Choose A.",
            question_type=QuestionType.MCQ,
            options={"A": "Correct", "B": "Wrong"},
            correct_answer="A",
            marks=Decimal("5.00"),
        )
    )
    db.session.add(exam)
    db.session.commit()
    return exam


def _submission(
    exam: Exam,
    email: str,
    *,
    finalized: bool,
) -> Submission:
    now = datetime.now(UTC)
    submission = Submission(
        exam=exam,
        candidate_name="Student User",
        candidate_email=email,
        responses={str(exam.questions[0].id): "A"},
        resume_token_hash=secrets.token_hex(32),
        started_at=now - timedelta(minutes=5),
        submitted_at=now if finalized else None,
    )
    db.session.add(submission)
    db.session.commit()
    return submission


def test_lecturer_dashboard_lists_only_owned_exams(client, admin):
    lecturer = _account("owner@mau.edu.ng", Role.LECTURER)
    owned = _exam(lecturer)
    _exam(admin)

    _login(client, lecturer)
    response = client.get("/lecturer/")

    assert response.status_code == 200
    assert owned.title.encode() in response.data
    assert response.data.count(b"Algorithms Examination") == 1


def test_student_dashboard_shows_attempt_and_released_result(client, admin):
    student = _account("student@student.mau.edu.ng", Role.STUDENT)
    exam = _exam(admin)
    active = _submission(exam, student.email, finalized=False)

    second_exam = _exam(admin)
    finalized = _submission(second_exam, student.email, finalized=True)

    _login(client, student)
    dashboard = client.get("/student/")

    assert dashboard.status_code == 200
    assert b"In progress" in dashboard.data
    assert b"Result released" in dashboard.data
    assert active.candidate_email.encode() not in dashboard.data

    result_page = client.get(f"/student/results/{finalized.id}")
    assert result_page.status_code == 200
    assert b"Final score" in result_page.data
    assert b"5.00 / 5.00" in result_page.data


def test_student_result_remains_pending_and_private(client, admin):
    student = _account("private@student.mau.edu.ng", Role.STUDENT)
    other = _account("other@student.mau.edu.ng", Role.STUDENT)
    scheduled_exam = _exam(admin, scheduled=True)
    submission = _submission(scheduled_exam, student.email, finalized=True)
    grade_submission(submission)
    db.session.commit()

    _login(client, student)
    pending = client.get(f"/student/results/{submission.id}")
    assert pending.status_code == 200
    assert b"not available yet" in pending.data

    client.post("/account/logout")
    _login(client, other)
    assert client.get(f"/student/results/{submission.id}").status_code == 404
    assert client.get("/student/results/99999").status_code == 404


def test_student_result_rejects_unfinished_attempt(client, admin):
    student = _account("unfinished@student.mau.edu.ng", Role.STUDENT)
    submission = _submission(_exam(admin), student.email, finalized=False)
    _login(client, student)

    assert client.get(f"/student/results/{submission.id}").status_code == 404

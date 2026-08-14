"""Tests for Phase 4 Admin examination and question management."""

from datetime import UTC, datetime
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


def _login(client):
    return client.post(
        "/admin/login",
        data={
            "email": "admin@mau.edu.ng",
            "password": "Phase3TestPassword!",
        },
    )


def _exam(
    admin,
    *,
    token="phase-four-token",
    title="Software Testing",
):
    exam = Exam(
        admin_id=admin.id,
        title=title,
        course_code="CSC 401",
        course_title="Software Quality Assurance",
        instructions="Answer every question.",
        time_limit_minutes=90,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token=token,
    )
    db.session.add(exam)
    db.session.commit()
    return exam


def _question(
    exam,
    *,
    position=1,
    question_type=QuestionType.MCQ,
    text="Which testing level examines one unit?",
):
    options = {
        "A": "Unit testing",
        "B": "System testing",
    }
    correct_answer = "A"

    if question_type is QuestionType.SHORT_ANSWER:
        options = None
        correct_answer = "Regression"
    elif question_type is QuestionType.OPEN_ENDED:
        options = None
        correct_answer = None

    question = Question(
        exam=exam,
        question_text=text,
        question_type=question_type,
        position=position,
        marks=Decimal("2.00"),
        options=options,
        correct_answer=correct_answer,
        short_answer_case_sensitive=False,
        short_answer_trim_whitespace=True,
    )
    db.session.add(question)
    db.session.commit()
    return question


def _exam_data(**overrides):
    data = {
        "title": "Introduction to Programming",
        "course_code": " csc 101 ",
        "course_title": "Computer Programming I",
        "instructions": " Read carefully. ",
        "time_limit_minutes": "60",
        "monitor_type": MonitorType.EYE_GAZE.value,
    }
    data.update(overrides)
    return data


def _question_data(
    question_type=QuestionType.MCQ,
    **overrides,
):
    data = {
        "question_text": " What is an algorithm? ",
        "question_type": question_type.value,
        "marks": "5.00",
        "mcq_option_a": " A finite procedure ",
        "mcq_option_b": "A programming language",
        "mcq_option_c": "",
        "mcq_option_d": " A database ",
        "correct_option": "A",
        "short_answer": "",
        "short_answer_case_sensitive": "y",
        "short_answer_trim_whitespace": "y",
    }
    data.update(overrides)
    return data


def test_exam_management_requires_admin_login(client, admin):
    exam = _exam(admin)
    question = _question(exam)

    paths = [
        ("get", "/admin/exams/new"),
        ("get", f"/admin/exams/{exam.id}"),
        ("get", f"/admin/exams/{exam.id}/edit"),
        ("post", f"/admin/exams/{exam.id}/delete"),
        ("get", f"/admin/exams/{exam.id}/questions/new"),
        (
            "get",
            f"/admin/exams/{exam.id}/questions/{question.id}/edit",
        ),
        (
            "post",
            f"/admin/exams/{exam.id}/questions/{question.id}/delete",
        ),
    ]

    for method, path in paths:
        response = getattr(client, method)(path)

        assert response.status_code == 302
        assert "/admin/login" in response.headers["Location"]


def test_dashboard_lists_examinations(client, admin):
    exam = _exam(admin)
    _question(exam)
    _login(client)

    response = client.get("/admin/")

    assert response.status_code == 200
    assert b"Software Testing" in response.data
    assert b"CSC 401" in response.data
    assert b"1 question(s)" in response.data
    assert b"Editable" in response.data


def test_create_exam_validates_and_generates_secure_token(
    client,
    admin,
    monkeypatch,
):
    _login(client)

    assert client.get("/admin/exams/new").status_code == 200

    invalid = client.post(
        "/admin/exams/new",
        data=_exam_data(
            title="",
            time_limit_minutes="0",
        ),
    )

    assert invalid.status_code == 200
    assert b"This field is required" in invalid.data
    assert b"Time limit must be between 1 and 1440 minutes" in (
        invalid.data
    )

    monkeypatch.setattr(
        "app.admin.exam_routes.secrets.token_urlsafe",
        lambda byte_count: f"secure-token-{byte_count}",
    )

    response = client.post(
        "/admin/exams/new",
        data=_exam_data(),
    )

    exam = db.session.scalar(select(Exam))

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/admin/exams/{exam.id}"
    )
    assert exam.admin_id == admin.id
    assert exam.course_code == "CSC 101"
    assert exam.instructions == "Read carefully."
    assert exam.time_limit_minutes == 60
    assert exam.monitor_type is MonitorType.EYE_GAZE
    assert exam.release_option is ReleaseOption.IMMEDIATE
    assert exam.scheduled_release_at is None
    assert exam.exam_link_token == "secure-token-32"


def test_exam_detail_and_candidate_share_link_use_token(
    client,
    admin,
):
    exam = _exam(admin)
    _login(client)

    detail = client.get(f"/admin/exams/{exam.id}")
    landing = client.get(f"/exam/{exam.exam_link_token}")

    assert detail.status_code == 200
    assert f"/exam/{exam.exam_link_token}".encode() in detail.data
    assert b"3 warnings" in detail.data
    assert b"Answer every question" in detail.data
    assert landing.status_code == 200
    assert b"Software Testing" in landing.data
    assert b"Candidate email verification will be activated in Phase 5" in (
        landing.data
    )
    assert client.get("/exam/not-a-real-token").status_code == 404


def test_edit_exam_loads_values_and_updates_settings(
    client,
    admin,
):
    exam = _exam(admin)
    _login(client)

    page = client.get(f"/admin/exams/{exam.id}/edit")

    assert page.status_code == 200
    assert b"Software Testing" in page.data

    response = client.post(
        f"/admin/exams/{exam.id}/edit",
        data=_exam_data(
            title="Advanced Testing",
            instructions="   ",
            monitor_type=MonitorType.FACE.value,
        ),
    )

    db.session.refresh(exam)

    assert response.status_code == 302
    assert exam.title == "Advanced Testing"
    assert exam.instructions is None
    assert exam.monitor_type is MonitorType.FACE


def test_delete_exam_removes_its_questions(client, admin):
    exam = _exam(admin)
    _question(exam)
    exam_id = exam.id
    _login(client)

    response = client.post(
        f"/admin/exams/{exam_id}/delete"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/")
    assert db.session.get(Exam, exam_id) is None
    assert db.session.scalar(select(Question)) is None


def test_question_form_reports_conditional_validation_errors(
    client,
    admin,
):
    exam = _exam(admin)
    _login(client)

    url = f"/admin/exams/{exam.id}/questions/new"

    assert client.get(url).status_code == 200

    required = client.post(
        url,
        data=_question_data(
            question_text="",
            marks="",
        ),
    )

    assert required.status_code == 200
    assert b"This field is required" in required.data

    missing_mcq = client.post(
        url,
        data=_question_data(
            mcq_option_a="",
            mcq_option_b="",
            correct_option="",
        ),
    )

    assert b"Option A is required" in missing_mcq.data
    assert b"Option B is required" in missing_mcq.data
    assert b"Select a correct option" in missing_mcq.data

    empty_selected_option = client.post(
        url,
        data=_question_data(correct_option="C"),
    )

    assert b"Select a correct option" in empty_selected_option.data

    missing_short_answer = client.post(
        url,
        data=_question_data(QuestionType.SHORT_ANSWER),
    )

    assert b"A correct short answer is required" in (
        missing_short_answer.data
    )
    assert db.session.scalar(select(Question)) is None


def test_create_all_supported_question_types_and_positions(
    client,
    admin,
):
    exam = _exam(admin)
    _login(client)

    url = f"/admin/exams/{exam.id}/questions/new"

    mcq = client.post(
        url,
        data=_question_data(),
    )

    short_answer = client.post(
        url,
        data=_question_data(
            QuestionType.SHORT_ANSWER,
            short_answer=" recursion ",
            short_answer_case_sensitive="y",
            short_answer_trim_whitespace="",
        ),
    )

    open_ended = client.post(
        url,
        data=_question_data(QuestionType.OPEN_ENDED),
    )

    assert [
        mcq.status_code,
        short_answer.status_code,
        open_ended.status_code,
    ] == [302, 302, 302]

    questions = db.session.scalars(
        select(Question).order_by(Question.position)
    ).all()

    assert [question.position for question in questions] == [1, 2, 3]

    assert questions[0].options == {
        "A": "A finite procedure",
        "B": "A programming language",
        "D": "A database",
    }
    assert questions[0].correct_answer == "A"

    assert questions[1].correct_answer == "recursion"
    assert questions[1].short_answer_case_sensitive is True
    assert questions[1].short_answer_trim_whitespace is False

    assert questions[2].options is None
    assert questions[2].correct_answer is None


def test_edit_forms_support_every_question_type(
    client,
    admin,
):
    exam = _exam(admin)

    mcq = _question(exam)

    short_answer = _question(
        exam,
        position=2,
        question_type=QuestionType.SHORT_ANSWER,
        text="Name a testing technique.",
    )

    open_ended = _question(
        exam,
        position=3,
        question_type=QuestionType.OPEN_ENDED,
        text="Explain software quality.",
    )

    _login(client)

    for question in (mcq, short_answer, open_ended):
        page = client.get(
            f"/admin/exams/{exam.id}/questions/{question.id}/edit"
        )

        assert page.status_code == 200
        assert question.question_text.encode() in page.data

    response = client.post(
        f"/admin/exams/{exam.id}/questions/{open_ended.id}/edit",
        data=_question_data(
            QuestionType.SHORT_ANSWER,
            short_answer=" Iteration ",
        ),
    )

    db.session.refresh(open_ended)

    assert response.status_code == 302
    assert open_ended.question_type is QuestionType.SHORT_ANSWER
    assert open_ended.question_text == "What is an algorithm?"
    assert open_ended.correct_answer == "Iteration"
    assert open_ended.options is None


def test_delete_question_removes_only_selected_question(
    client,
    admin,
):
    exam = _exam(admin)

    first = _question(exam)

    second = _question(
        exam,
        position=2,
        text="Define verification.",
    )

    _login(client)

    response = client.post(
        f"/admin/exams/{exam.id}/questions/{first.id}/delete"
    )

    assert response.status_code == 302
    assert db.session.get(Question, first.id) is None
    assert db.session.get(Question, second.id) is not None


def test_missing_or_mismatched_resources_return_not_found(
    client,
    admin,
):
    first_exam = _exam(admin)

    second_exam = _exam(
        admin,
        token="second-token",
        title="Second exam",
    )

    question = _question(second_exam)
    _login(client)

    assert client.get("/admin/exams/99999").status_code == 404

    response = client.get(
        f"/admin/exams/{first_exam.id}/questions/{question.id}/edit"
    )

    assert response.status_code == 404


def test_started_submission_locks_every_structural_write(
    client,
    admin,
):
    exam = _exam(admin)
    question = _question(exam)

    submission = Submission(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email="amina@example.com",
        responses={},
        resume_token_hash="a" * 64,
        started_at=datetime.now(UTC),
        warn_count=0,
    )

    db.session.add(submission)
    db.session.commit()
    _login(client)

    detail = client.get(f"/admin/exams/{exam.id}")

    assert detail.status_code == 200
    assert b"Locked" in detail.data
    assert b"no longer be edited or deleted" in detail.data

    locked_requests = [
        (
            "get",
            f"/admin/exams/{exam.id}/edit",
            None,
        ),
        (
            "post",
            f"/admin/exams/{exam.id}/edit",
            _exam_data(),
        ),
        (
            "post",
            f"/admin/exams/{exam.id}/delete",
            None,
        ),
        (
            "get",
            f"/admin/exams/{exam.id}/questions/new",
            None,
        ),
        (
            "post",
            f"/admin/exams/{exam.id}/questions/new",
            _question_data(),
        ),
        (
            "get",
            (
                f"/admin/exams/{exam.id}/questions/"
                f"{question.id}/edit"
            ),
            None,
        ),
        (
            "post",
            (
                f"/admin/exams/{exam.id}/questions/"
                f"{question.id}/edit"
            ),
            _question_data(),
        ),
        (
            "post",
            (
                f"/admin/exams/{exam.id}/questions/"
                f"{question.id}/delete"
            ),
            None,
        ),
    ]

    for method, path, data in locked_requests:
        response = getattr(client, method)(
            path,
            data=data,
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith(
            f"/admin/exams/{exam.id}"
        )

    assert db.session.get(Exam, exam.id) is not None
    assert db.session.get(Question, question.id) is not None
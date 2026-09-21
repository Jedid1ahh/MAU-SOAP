"""Tests for Phase 9 automatic grading and Admin manual review."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.candidate.services import credential_digest
from app.candidate.session_services import (
    finalize_submission,
    finalize_warning_limit,
)
from app.extensions import db
from app.grading import (
    InvalidManualGradeError,
    assign_manual_grade,
    automatic_marks,
    grade_submission,
)
from app.models import (
    AnswerGrade,
    Exam,
    GradedBy,
    MonitorType,
    Question,
    QuestionType,
    ReleaseOption,
    Result,
    ResultStatus,
    Submission,
)
from tests.helpers import course_for


def _exam(admin, *, token="grading-exam", include_open=True):
    exam = Exam(
        admin_id=admin.id,
        course=course_for(admin, "CSC 420", "Distributed Systems"),
        title="Distributed Systems",
        course_code="CSC 420",
        course_title="Distributed Systems",
        time_limit_minutes=30,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token=token,
    )
    db.session.add(exam)
    db.session.flush()
    questions = [
        Question(
            exam=exam,
            question_text="Which protocol is reliable?",
            question_type=QuestionType.MCQ,
            position=1,
            marks=Decimal("2.00"),
            options={"A": "UDP", "B": "TCP"},
            correct_answer="B",
        ),
        Question(
            exam=exam,
            question_text="Expand HTTP.",
            question_type=QuestionType.SHORT_ANSWER,
            position=2,
            marks=Decimal("3.00"),
            correct_answer="Hypertext Transfer Protocol",
            short_answer_case_sensitive=False,
            short_answer_trim_whitespace=True,
        ),
    ]
    if include_open:
        questions.append(
            Question(
                exam=exam,
                question_text="Explain eventual consistency.",
                question_type=QuestionType.OPEN_ENDED,
                position=3,
                marks=Decimal("5.00"),
            )
        )
    db.session.add_all(questions)
    db.session.commit()
    return exam


def _responses(exam, *, mcq="B", short=" hypertext transfer protocol "):
    responses = {
        str(exam.questions[0].id): mcq,
        str(exam.questions[1].id): short,
    }
    if len(exam.questions) > 2:
        responses[str(exam.questions[2].id)] = (
            "Replicas converge after updates stop."
        )
    return responses


def _submission(
    exam,
    *,
    email="candidate@gmail.com",
    responses=None,
    finalized=True,
):
    submission = Submission(
        exam=exam,
        candidate_name="Amina Bello",
        candidate_email=email,
        responses=responses or {},
        resume_token_hash=credential_digest(f"resume-{email}"),
        started_at=datetime.now(UTC),
        submitted_at=datetime.now(UTC) if finalized else None,
        submission_reason="manual" if finalized else None,
    )
    db.session.add(submission)
    db.session.commit()
    return submission


def _login(client, lecturer):
    response = client.post(
        "/account/login",
        data={
            "email": lecturer.email,
            "password": "LecturerTestPassword!",
        },
    )
    assert response.status_code == 302


def _pending_grade(submission):
    return next(
        grade
        for grade in submission.answer_grades
        if grade.awarded_marks is None
    )


def test_automatic_matching_rules(admin):
    exam = _exam(admin)
    mcq, short_answer, open_answer = exam.questions

    assert automatic_marks(mcq, "B") == Decimal("2.00")
    assert automatic_marks(mcq, "b") == Decimal("0.00")
    assert automatic_marks(short_answer, " HYPERTEXT TRANSFER PROTOCOL ") == (
        Decimal("3.00")
    )
    assert automatic_marks(short_answer, "HTTP") == Decimal("0.00")
    assert automatic_marks(open_answer, "Any essay") is None

    short_answer.short_answer_case_sensitive = True
    assert automatic_marks(short_answer, "hypertext transfer protocol") == (
        Decimal("0.00")
    )
    short_answer.short_answer_case_sensitive = False
    short_answer.short_answer_trim_whitespace = False
    assert automatic_marks(short_answer, " Hypertext Transfer Protocol ") == (
        Decimal("0.00")
    )


def test_grade_submission_creates_one_row_per_question_and_pending_result(admin):
    exam = _exam(admin)
    submission = _submission(
        exam,
        responses=_responses(exam),
    )

    result = grade_submission(submission)
    db.session.commit()

    assert len(submission.answer_grades) == 3
    assert [grade.awarded_marks for grade in submission.answer_grades] == [
        Decimal("2.00"),
        Decimal("3.00"),
        None,
    ]
    assert [grade.graded_by for grade in submission.answer_grades] == [
        GradedBy.AUTOMATIC,
        GradedBy.AUTOMATIC,
        None,
    ]
    assert submission.answer_grades[0].graded_at == submission.submitted_at
    assert result.marks_obtained == Decimal("5.00")
    assert result.total_marks == Decimal("10.00")
    assert result.percentage == Decimal("50.00")
    assert result.status is ResultStatus.PENDING_MANUAL_REVIEW
    assert result.released_at is None

    grade_submission(submission)
    db.session.commit()
    assert db.session.scalar(select(func.count(AnswerGrade.id))) == 3
    assert db.session.scalar(select(func.count(Result.id))) == 1


def test_fully_automatic_submission_is_complete_and_rounds_percentage(admin):
    exam = _exam(admin, include_open=False)
    exam.questions[0].marks = Decimal("1.00")
    exam.questions[1].marks = Decimal("2.00")
    submission = _submission(
        exam,
        responses=_responses(exam, mcq="A"),
    )

    result = grade_submission(submission)
    db.session.commit()

    assert result.marks_obtained == Decimal("2.00")
    assert result.total_marks == Decimal("3.00")
    assert result.percentage == Decimal("66.67")
    assert result.status is ResultStatus.COMPLETE


def test_unanswered_automatic_questions_receive_zero(admin):
    exam = _exam(admin, include_open=False)
    submission = _submission(exam)

    result = grade_submission(submission)
    db.session.commit()

    assert result.marks_obtained == Decimal("0.00")
    assert result.percentage == Decimal("0.00")
    assert result.status is ResultStatus.COMPLETE


def test_empty_finalized_exam_produces_zero_complete_result(admin):
    exam = Exam(
        admin_id=admin.id,
        course=course_for(admin, "LEG 000", "Legacy data"),
        title="Empty legacy examination",
        course_code="LEG 000",
        course_title="Legacy data",
        time_limit_minutes=30,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token="empty-legacy-exam",
    )
    db.session.add(exam)
    db.session.commit()
    submission = _submission(exam)

    result = grade_submission(submission)
    db.session.commit()

    assert result.marks_obtained == Decimal("0.00")
    assert result.total_marks == Decimal("0.00")
    assert result.percentage == Decimal("0.00")
    assert result.status is ResultStatus.COMPLETE


def test_active_submission_cannot_be_graded(admin):
    exam = _exam(admin)
    submission = _submission(exam, finalized=False)

    with pytest.raises(ValueError, match="Only finalized"):
        grade_submission(submission)


def test_manual_grade_completes_result_and_preserves_automatic_marks(admin):
    exam = _exam(admin)
    submission = _submission(exam, responses=_responses(exam))
    grade_submission(submission)
    pending = _pending_grade(submission)

    result = assign_manual_grade(
        pending,
        Decimal("4.25"),
        admin,
        "  Clear explanation.  ",
    )
    db.session.commit()

    assert pending.awarded_marks == Decimal("4.25")
    assert pending.graded_by is GradedBy.LECTURER
    assert pending.grader is admin
    assert pending.graded_at is not None
    assert pending.feedback == "Clear explanation."
    assert result.marks_obtained == Decimal("9.25")
    assert result.percentage == Decimal("92.50")
    assert result.status is ResultStatus.COMPLETE

    grade_submission(submission)
    assert pending.awarded_marks == Decimal("4.25")
    assert pending.graded_by is GradedBy.LECTURER


@pytest.mark.parametrize(
    "marks,error",
    [
        (Decimal("-0.01"), "between 0"),
        (Decimal("5.01"), "between 0"),
        ("not-a-mark", "valid mark"),
        (Decimal("NaN"), "valid mark"),
        (Decimal("Infinity"), "valid mark"),
    ],
)
def test_manual_grade_rejects_invalid_marks(admin, marks, error):
    exam = _exam(admin)
    submission = _submission(exam, responses=_responses(exam))
    grade_submission(submission)
    pending = _pending_grade(submission)

    with pytest.raises(InvalidManualGradeError, match=error):
        assign_manual_grade(pending, marks, admin)

    assert pending.awarded_marks is None
    assert submission.result.status is ResultStatus.PENDING_MANUAL_REVIEW


def test_manual_grade_rejects_automatic_question(admin):
    exam = _exam(admin)
    submission = _submission(exam, responses=_responses(exam))
    grade_submission(submission)
    automatic_grade = submission.answer_grades[0]

    with pytest.raises(InvalidManualGradeError, match="open-ended"):
        assign_manual_grade(
            automatic_grade,
            Decimal("1.00"),
            admin,
        )


def test_finalization_services_grade_manual_and_warning_submissions(admin):
    manual_exam = _exam(admin, token="manual-finalization")
    manual = _submission(manual_exam, finalized=False)
    finalize_submission(manual, _responses(manual_exam))
    db.session.commit()

    warning_exam = _exam(admin, token="warning-finalization")
    warning = _submission(
        warning_exam,
        email="warning@gmail.com",
        finalized=False,
    )
    finalize_warning_limit(warning, _responses(warning_exam))
    db.session.commit()

    assert len(manual.answer_grades) == 3
    assert manual.result.status is ResultStatus.PENDING_MANUAL_REVIEW
    assert len(warning.answer_grades) == 3
    assert warning.result.status is ResultStatus.PENDING_MANUAL_REVIEW


def test_lecturer_queue_backfills_and_lists_only_pending_submissions(
    client, lecturer
):
    pending_exam = _exam(lecturer, token="pending-queue")
    pending = _submission(
        pending_exam,
        responses=_responses(pending_exam),
    )
    complete_exam = _exam(
        lecturer,
        token="complete-queue",
        include_open=False,
    )
    complete = _submission(
        complete_exam,
        email="complete@gmail.com",
        responses=_responses(complete_exam),
    )
    assert pending.result is None
    assert complete.result is None
    _login(client, lecturer)

    response = client.get("/lecturer/grading")

    assert response.status_code == 200
    assert b"Pending grading" in response.data
    assert b"Amina Bello" in response.data
    assert b"pending-queue" not in response.data
    assert pending.result.status is ResultStatus.PENDING_MANUAL_REVIEW
    assert complete.result.status is ResultStatus.COMPLETE
    assert response.data.count(b"Review responses") == 1


def test_empty_grading_queue_and_dashboard_navigation(client, lecturer):
    _login(client, lecturer)

    dashboard = client.get("/lecturer/")
    queue = client.get("/lecturer/grading")

    assert dashboard.status_code == 200
    assert b"Pending grading" in dashboard.data
    assert queue.status_code == 200
    assert b"No responses are awaiting review" in queue.data


def test_grading_routes_require_lecturer_login(client, lecturer):
    exam = _exam(lecturer)
    submission = _submission(exam, responses=_responses(exam))

    queue = client.get("/lecturer/grading")
    detail = client.get(f"/lecturer/grading/submissions/{submission.id}")

    assert queue.status_code == 302
    assert "/account/login" in queue.headers["Location"]
    assert detail.status_code == 302
    assert "/account/login" in detail.headers["Location"]


def test_lecturer_can_review_and_grade_open_response(client, lecturer):
    exam = _exam(lecturer)
    submission = _submission(exam, responses=_responses(exam))
    _login(client, lecturer)

    detail = client.get(f"/lecturer/grading/submissions/{submission.id}")
    pending = _pending_grade(submission)

    assert detail.status_code == 200
    assert b"Candidate responses" in detail.data
    assert b"Replicas converge after updates stop." in detail.data
    assert b"Pending Manual Review" in detail.data
    assert b"Result release is handled" in detail.data

    response = client.post(
        (
            f"/lecturer/grading/submissions/{submission.id}"
            f"/answers/{pending.id}"
        ),
        data={
            "awarded_marks": "4.50",
            "feedback": "Good comparison.",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/lecturer/grading/submissions/{submission.id}"
    )
    assert pending.awarded_marks == Decimal("4.50")
    assert pending.feedback == "Good comparison."
    assert submission.result.status is ResultStatus.COMPLETE

    completed = client.get(response.headers["Location"])
    assert b"Complete" in completed.data
    assert b"9.50 / 10.00" in completed.data

    queue = client.get("/lecturer/grading")
    assert b"No responses are awaiting review" in queue.data


@pytest.mark.parametrize(
    "data,expected_message",
    [
        ({"awarded_marks": "-1"}, b"cannot be negative"),
        ({"awarded_marks": "6"}, b"between 0 and 5.00"),
        ({"awarded_marks": "invalid"}, b"Not a valid decimal value"),
        (
            {
                "awarded_marks": "4",
                "feedback": "x" * 5001,
            },
            b"Field cannot be longer than 5000 characters",
        ),
    ],
)
def test_manual_grading_endpoint_rejects_invalid_forms(
    client,
    lecturer,
    data,
    expected_message,
):
    exam = _exam(lecturer)
    submission = _submission(exam, responses=_responses(exam))
    grade_submission(submission)
    db.session.commit()
    pending = _pending_grade(submission)
    _login(client, lecturer)

    response = client.post(
        (
            f"/lecturer/grading/submissions/{submission.id}"
            f"/answers/{pending.id}"
        ),
        data=data,
    )

    assert response.status_code == 400
    assert expected_message in response.data
    refreshed = db.session.get(AnswerGrade, pending.id)
    assert refreshed.awarded_marks is None


def test_manual_grading_rejects_unknown_mismatched_and_automatic_grades(
    client,
    lecturer,
):
    first_exam = _exam(lecturer, token="first-grading")
    first = _submission(first_exam, responses=_responses(first_exam))
    grade_submission(first)
    second_exam = _exam(lecturer, token="second-grading")
    second = _submission(
        second_exam,
        email="second@gmail.com",
        responses=_responses(second_exam),
    )
    grade_submission(second)
    db.session.commit()
    second_pending = _pending_grade(second)
    first_automatic = first.answer_grades[0]
    _login(client, lecturer)

    unknown_submission = client.get("/lecturer/grading/submissions/999999")
    mismatched = client.post(
        (
            f"/lecturer/grading/submissions/{first.id}"
            f"/answers/{second_pending.id}"
        ),
        data={"awarded_marks": "1"},
    )
    automatic = client.post(
        (
            f"/lecturer/grading/submissions/{first.id}"
            f"/answers/{first_automatic.id}"
        ),
        data={"awarded_marks": "1"},
    )

    assert unknown_submission.status_code == 404
    assert mismatched.status_code == 404
    assert automatic.status_code == 404


def test_nonfinal_submission_is_not_available_for_lecturer_grading(
    client, lecturer
):
    exam = _exam(lecturer)
    active = _submission(exam, finalized=False)
    _login(client, lecturer)

    response = client.get(f"/lecturer/grading/submissions/{active.id}")

    assert response.status_code == 404

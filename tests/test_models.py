"""Phase 2 database-model tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AnswerGrade,
    Exam,
    GradedBy,
    MonitorType,
    PasswordResetToken,
    Question,
    QuestionType,
    ReleaseOption,
    Result,
    ResultStatus,
    Role,
    Submission,
    User,
    VerificationToken,
    ViolationType,
    WarningLog,
)


def _admin() -> User:
    admin = User(
        email="admin@mau.edu.ng",
        password_hash="not-a-plaintext-password",
        role=Role.ADMIN,
    )
    db.session.add(admin)
    db.session.flush()
    return admin


def _exam(admin: User, token: str = "exam-token") -> Exam:
    exam = Exam(
        admin=admin,
        title="Data Structures Examination",
        course_code="CSC 301",
        course_title="Data Structures",
        time_limit_minutes=60,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token=token,
    )
    db.session.add(exam)
    db.session.flush()
    return exam


def _submission(exam: Exam, email: str = "candidate@gmail.com") -> Submission:
    submission = Submission(
        exam=exam,
        candidate_name="Test Candidate",
        candidate_email=email,
        responses={"1": "B"},
        resume_token_hash="a" * 64,
        started_at=datetime.now(UTC),
    )
    db.session.add(submission)
    db.session.flush()
    return submission


def test_all_phase_2_tables_are_created(app):
    inspector = db.inspect(db.engine)

    assert {
        "users",
        "exams",
        "questions",
        "submissions",
        "results",
        "warning_logs",
        "verification_tokens",
        "password_reset_tokens",
        "answer_grades",
    } <= set(inspector.get_table_names())


def test_enum_values_and_json_round_trip(app):
    admin = _admin()
    exam = _exam(admin)
    question = Question(
        exam=exam,
        position=1,
        question_text="Choose the correct key.",
        question_type=QuestionType.MCQ,
        options={"A": "Wrong", "B": "Correct"},
        correct_answer="B",
        marks=Decimal("2.00"),
    )
    db.session.add(question)
    db.session.commit()

    db.session.expire_all()
    saved = db.session.get(Question, question.id)

    assert saved is not None
    assert saved.question_type is QuestionType.MCQ
    assert saved.options == {"A": "Wrong", "B": "Correct"}
    assert saved.exam.monitor_type is MonitorType.FACE
    assert "Question" in repr(saved)
    assert "Exam" in repr(saved.exam)
    assert "User" in repr(saved.exam.admin)


def test_exam_link_token_is_unique(app):
    admin = _admin()
    _exam(admin, token="same-token")

    with pytest.raises(IntegrityError):
        _exam(admin, token="same-token")


def test_candidate_can_have_only_one_submission_per_exam(app):
    exam = _exam(_admin())
    _submission(exam)

    duplicate = Submission(
        exam=exam,
        candidate_name="Same Candidate",
        candidate_email="candidate@gmail.com",
        responses={},
        resume_token_hash="b" * 64,
        started_at=datetime.now(UTC),
    )
    db.session.add(duplicate)

    with pytest.raises(IntegrityError):
        db.session.commit()


def test_started_submission_locks_exam(app):
    exam = _exam(_admin())
    assert exam.is_locked is False

    submission = _submission(exam)

    assert exam.is_locked is True
    assert submission.is_finalized is False
    assert "Submission" in repr(submission)


def test_warning_and_grading_relationships(app):
    exam = _exam(_admin())
    question = Question(
        exam=exam,
        position=1,
        question_text="Explain ACID.",
        question_type=QuestionType.OPEN_ENDED,
        marks=Decimal("10.00"),
    )
    db.session.add(question)
    db.session.flush()

    submission = _submission(exam)
    warning = WarningLog(
        submission=submission,
        violation_type=ViolationType.FOCUS_LOSS,
        metadata_json={"visibility": "hidden"},
    )
    grade = AnswerGrade(
        submission=submission,
        question=question,
        awarded_marks=Decimal("8.00"),
        graded_by=GradedBy.ADMIN,
        grader=exam.admin,
        graded_at=datetime.now(UTC),
    )
    result = Result(
        submission=submission,
        marks_obtained=Decimal("8.00"),
        total_marks=Decimal("10.00"),
        percentage=Decimal("80.00"),
        status=ResultStatus.COMPLETE,
    )
    db.session.add_all([warning, grade, result])
    db.session.commit()

    assert submission.warning_logs == [warning]
    assert submission.answer_grades == [grade]
    assert submission.result is result
    assert result.is_released is False
    assert "WarningLog" in repr(warning)
    assert "AnswerGrade" in repr(grade)
    assert "Result" in repr(result)


def test_verification_token_locks_after_five_attempts(app):
    exam = _exam(_admin())
    token = VerificationToken(
        exam=exam,
        candidate_name="Test Candidate",
        candidate_email="candidate@gmail.com",
        otp_hash="c" * 64,
        magic_token_hash="d" * 64,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        attempts=5,
    )

    assert token.is_locked is True
    assert "VerificationToken" in repr(token)


def test_password_reset_token_state(app):
    admin = _admin()
    token = PasswordResetToken(
        user=admin,
        token_hash="e" * 64,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        attempts=0,
    )

    assert token.is_locked is False
    assert token.is_used is False
    assert "PasswordResetToken" in repr(token)
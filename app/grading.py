"""Server-authoritative automatic and manual grading services."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.extensions import db
from app.models import (
    AnswerGrade,
    GradedBy,
    Question,
    QuestionType,
    Result,
    ResultStatus,
    Submission,
    User,
)
from app.result_release import synchronize_result_release

MARK_PRECISION = Decimal("0.01")


class InvalidManualGradeError(ValueError):
    """Raised when an Admin mark is outside the question's valid range."""


def utc_now() -> datetime:
    """Return one timezone-aware UTC timestamp for grading records."""

    return datetime.now(UTC)


def _normalized_short_answer(question: Question, answer: str) -> str:
    """Apply the question's configured short-answer comparison rules."""

    normalized = answer
    if question.short_answer_trim_whitespace:
        normalized = normalized.strip()
    if not question.short_answer_case_sensitive:
        normalized = normalized.casefold()
    return normalized


def automatic_marks(question: Question, response: str) -> Decimal | None:
    """Return automatic marks, leaving open-ended responses ungraded."""

    if question.question_type is QuestionType.OPEN_ENDED:
        return None

    is_correct = False
    if question.question_type is QuestionType.MCQ:
        is_correct = response == (question.correct_answer or "")
    elif question.question_type is QuestionType.SHORT_ANSWER:
        is_correct = _normalized_short_answer(
            question,
            response,
        ) == _normalized_short_answer(
            question,
            question.correct_answer or "",
        )
    else:  # pragma: no cover - database enum validation prevents this state
        raise ValueError("Unsupported question type.")

    return question.marks if is_correct else Decimal("0.00")


def recompute_result(submission: Submission) -> Result:
    """Recalculate totals and completion state from per-question grades."""

    questions = list(submission.exam.questions)
    grades_by_question = {
        grade.question_id: grade for grade in submission.answer_grades
    }
    total_marks = sum(
        (question.marks for question in questions),
        start=Decimal("0.00"),
    )
    marks_obtained = sum(
        (
            grade.awarded_marks
            for grade in grades_by_question.values()
            if grade.awarded_marks is not None
        ),
        start=Decimal("0.00"),
    )
    every_question_graded = len(grades_by_question) == len(questions) and all(
        grades_by_question[question.id].awarded_marks is not None
        for question in questions
    )
    percentage = Decimal("0.00")
    if total_marks > 0:
        percentage = (
            marks_obtained * Decimal("100") / total_marks
        ).quantize(MARK_PRECISION, rounding=ROUND_HALF_UP)

    result = submission.result
    if result is None:
        result = Result(submission=submission)
        db.session.add(result)

    result.marks_obtained = marks_obtained
    result.total_marks = total_marks
    result.percentage = percentage
    result.status = (
        ResultStatus.COMPLETE
        if every_question_graded
        else ResultStatus.PENDING_MANUAL_REVIEW
    )
    synchronize_result_release(result)
    return result


def grade_submission(submission: Submission) -> Result:
    """Create or repair one complete grading record set for a submission."""

    if not submission.is_finalized:
        raise ValueError("Only finalized submissions can be graded.")

    existing_grades = {
        grade.question_id: grade for grade in submission.answer_grades
    }
    responses = submission.responses or {}

    for question in submission.exam.questions:
        grade = existing_grades.get(question.id)
        if grade is None:
            grade = AnswerGrade(
                submission=submission,
                question=question,
            )
            db.session.add(grade)
            existing_grades[question.id] = grade

        if question.question_type is QuestionType.OPEN_ENDED:
            continue

        grade.awarded_marks = automatic_marks(
            question,
            responses.get(str(question.id), ""),
        )
        grade.graded_by = GradedBy.AUTOMATIC
        grade.grader = None
        grade.feedback = None
        grade.graded_at = submission.submitted_at or utc_now()

    db.session.flush()
    return recompute_result(submission)


def assign_manual_grade(
    grade: AnswerGrade,
    awarded_marks: Decimal,
    grader: User,
    feedback: str | None = None,
) -> Result:
    """Assign a bounded Admin mark and refresh the aggregate result."""

    if grade.question.question_type is not QuestionType.OPEN_ENDED:
        raise InvalidManualGradeError(
            "Only open-ended answers can be graded manually."
        )

    try:
        normalized_marks = Decimal(awarded_marks).quantize(
            MARK_PRECISION,
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, TypeError, ValueError) as error:
        raise InvalidManualGradeError("Enter a valid mark.") from error

    if not normalized_marks.is_finite():
        raise InvalidManualGradeError("Enter a valid mark.")
    if normalized_marks < 0 or normalized_marks > grade.question.marks:
        raise InvalidManualGradeError(
            f"Marks must be between 0 and {grade.question.marks}."
        )

    grade.awarded_marks = normalized_marks
    grade.graded_by = GradedBy.ADMIN
    grade.grader = grader
    grade.feedback = (feedback or "").strip() or None
    grade.graded_at = utc_now()
    return recompute_result(grade.submission)
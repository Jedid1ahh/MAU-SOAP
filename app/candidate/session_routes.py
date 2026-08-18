"""Phase 6 Candidate start, timing, question, and submission routes."""

from __future__ import annotations

from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select

from app.extensions import db
from app.models import Exam, QuestionType

from . import candidate_bp
from .services import resolve_candidate_session
from .session_services import (
    ExistingAttemptError,
    FinalizedSubmissionError,
    finalize_expired_submission,
    finalize_submission,
    remaining_seconds,
    resolve_submission_session,
    start_submission,
    submission_deadline,
)


def _exam_by_token(token: str) -> Exam:
    exam = db.session.scalar(
        select(Exam).where(
            Exam.exam_link_token == token
        )
    )

    if exam is None:
        abort(404)

    return exam


def _access_session_key(exam: Exam) -> str:
    return f"candidate_access_token_{exam.id}"


def _raw_session_token(
    exam: Exam,
) -> str | None:
    raw_token = session.get(
        _access_session_key(exam)
    )

    return (
        raw_token
        if isinstance(raw_token, str)
        else None
    )


def _submission_for_request(exam: Exam):
    return resolve_submission_session(
        exam,
        _raw_session_token(exam),
    )


def _question_payload(
    exam: Exam,
) -> list[dict]:
    """Serialize questions without grading answers or matching rules."""

    payload = []

    for question in exam.questions:
        item = {
            "id": question.id,
            "position": question.position,
            "question_text": question.question_text,
            "question_type": question.question_type.value,
            "marks": str(question.marks),
        }

        if question.question_type is QuestionType.MCQ:
            item["options"] = question.options or {}

        payload.append(item)

    return payload


def _response_payload(
    exam: Exam,
) -> dict[str, str]:
    """Accept answers only for known questions and valid MCQ keys."""

    responses = {}

    for question in exam.questions:
        answer = request.form.get(
            f"question_{question.id}",
            "",
        )

        if len(answer) > 10_000:
            abort(400)

        if (
            question.question_type is QuestionType.MCQ
            and answer
            and answer not in (question.options or {})
        ):
            abort(400)

        responses[str(question.id)] = answer

    return responses


@candidate_bp.post("/<token>/start")
def start_exam(token: str):
    """Start or reopen the verified Candidate's one attempt."""

    exam = _exam_by_token(token)
    raw_token = _raw_session_token(exam)

    verification = resolve_candidate_session(
        exam,
        raw_token,
    )

    if verification is None or raw_token is None:
        flash(
            "Verify your email address before starting this examination.",
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_landing",
                token=token,
            )
        )

    if not exam.questions:
        flash(
            "This examination does not contain any questions yet.",
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_ready",
                token=token,
            )
        )

    try:
        submission, created = start_submission(
            exam,
            verification,
            raw_token,
        )
    except ExistingAttemptError:
        db.session.rollback()

        flash(
            "An examination attempt already exists for this email address.",
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_landing",
                token=token,
            )
        )

    db.session.commit()

    # Once an examination starts, retain the browser-session token for
    # the entire browser session instead of using the verification
    # token's short permanent-cookie lifetime.
    session.permanent = False

    if submission.is_finalized:
        return redirect(
            url_for(
                "candidate.submission_received",
                token=token,
            )
        )

    if created:
        flash(
            "Examination started. The server timer is now running.",
            "success",
        )

    return redirect(
        url_for(
            "candidate.exam_session",
            token=token,
        )
    )


@candidate_bp.get("/<token>/session")
def exam_session(token: str):
    """Render the active session shell for the matching token."""

    exam = _exam_by_token(token)
    submission = _submission_for_request(exam)

    if submission is None:
        flash(
            "Start the examination before opening the question page.",
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_landing",
                token=token,
            )
        )

    if (
        submission.is_finalized
        or finalize_expired_submission(submission)
    ):
        db.session.commit()

        return redirect(
            url_for(
                "candidate.submission_received",
                token=token,
            )
        )

    return render_template(
        "candidate/exam_session.html",
        exam=exam,
        submission=submission,
        initial_remaining_seconds=remaining_seconds(
            submission
        ),
    )


@candidate_bp.get("/<token>/session/questions")
def session_questions(token: str):
    """Return answer-free questions to the matching active session."""

    exam = _exam_by_token(token)
    submission = _submission_for_request(exam)

    if submission is None:
        return jsonify(
            error="Candidate session required."
        ), 403

    if (
        submission.is_finalized
        or finalize_expired_submission(submission)
    ):
        db.session.commit()

        return jsonify(
            submitted=True,
            reason=submission.submission_reason,
        ), 409

    return jsonify(
        questions=_question_payload(exam)
    )


@candidate_bp.get("/<token>/session/time")
def session_time(token: str):
    """Return time calculated only from server-controlled values."""

    exam = _exam_by_token(token)
    submission = _submission_for_request(exam)

    if submission is None:
        return jsonify(
            error="Candidate session required."
        ), 403

    expired = finalize_expired_submission(
        submission
    )

    if expired:
        db.session.commit()

    return jsonify(
        remaining_seconds=remaining_seconds(
            submission
        ),
        deadline=submission_deadline(
            submission
        ).isoformat(),
        submitted=submission.is_finalized,
        reason=submission.submission_reason,
    )


@candidate_bp.post("/<token>/session/submit")
def submit_exam(token: str):
    """Accept the Candidate's answers once before server expiry."""

    exam = _exam_by_token(token)
    submission = _submission_for_request(exam)

    if submission is None:
        flash(
            "Candidate session not found.",
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_landing",
                token=token,
            )
        )

    if submission.is_finalized:
        abort(409)

    responses = _response_payload(exam)

    try:
        finalize_submission(
            submission,
            responses,
        )
    except FinalizedSubmissionError:
        db.session.commit()
        abort(409)

    db.session.commit()

    flash(
        "Your examination was submitted successfully.",
        "success",
    )

    return redirect(
        url_for(
            "candidate.submission_received",
            token=token,
        )
    )


@candidate_bp.get("/<token>/submitted")
def submission_received(token: str):
    """Confirm receipt without exposing grading before Phase 9."""

    exam = _exam_by_token(token)
    submission = _submission_for_request(exam)

    if (
        submission is None
        or not submission.is_finalized
    ):
        flash(
            "No finalized submission was found.",
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_landing",
                token=token,
            )
        )

    return render_template(
        "candidate/submission_received.html",
        exam=exam,
        submission=submission,
    )
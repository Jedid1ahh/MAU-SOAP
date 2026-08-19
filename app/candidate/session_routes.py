"""Candidate timing, question, submission, and supervision routes."""

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
from app.models import (
    Exam,
    QuestionType,
    Submission,
    ViolationType,
    WarningLog,
)

from . import candidate_bp
from .evidence_services import (
    EvidenceTooLargeError,
    InvalidEvidenceError,
    attach_face_absence_evidence,
)
from .services import resolve_candidate_session
from .session_services import (
    ExistingAttemptError,
    FinalizedSubmissionError,
    finalize_expired_submission,
    finalize_submission,
    finalize_warning_limit,
    remaining_seconds,
    resolve_submission_session,
    start_submission,
    submission_deadline,
)
from .supervision_services import (
    WARNING_LIMIT,
    InvalidViolationError,
    WarningLimitReachedError,
    record_warning,
    sanitize_metadata,
    violation_type_for_exam,
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


def _lock_submission(
    submission: Submission,
) -> Submission:
    """Lock one attempt while its warning counter is updated."""

    return db.session.scalar(
        select(Submission)
        .where(
            Submission.id == submission.id
        )
        .with_for_update()
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
            question.question_type
            is QuestionType.MCQ
            and answer
            and answer
            not in (question.options or {})
        ):
            abort(400)

        responses[str(question.id)] = answer

    return responses

def _supervision_response_payload(
    exam: Exam,
    raw_responses: object,
) -> dict[str, str]:
    """Keep valid current answers when the warning limit submits an attempt."""

    if not isinstance(raw_responses, dict):
        return {}

    responses = {}

    for question in exam.questions:
        answer = raw_responses.get(
            str(question.id),
            "",
        )

        if (
            not isinstance(answer, str)
            or len(answer) > 10_000
        ):
            answer = ""

        if (
            question.question_type
            is QuestionType.MCQ
            and answer
            and answer
            not in (question.options or {})
        ):
            answer = ""

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

    if request.form.get("supervision_consent") != "yes":
        flash(
            "You must consent to the disclosed camera supervision and "
            "face-absence evidence recording before starting.",
            "error",
        )
        return redirect(
            url_for("candidate.exam_ready", token=token)
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
    """Return remaining time from server-controlled values."""

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


@candidate_bp.post(
    "/<token>/session/violations"
)
def report_violation(token: str):
    """Validate and persist one active-session supervision event."""

    exam = _exam_by_token(token)
    submission = _submission_for_request(exam)

    if submission is None:
        return jsonify(
            error="Candidate session required."
        ), 403

    submission = _lock_submission(
        submission
    )

    if (
        submission.is_finalized
        or finalize_expired_submission(
            submission
        )
    ):
        db.session.commit()

        return jsonify(
            submitted=True,
            reason=submission.submission_reason,
        ), 409

    payload = request.get_json(
        silent=True
    )

    if not isinstance(payload, dict):
        return jsonify(
            error=(
                "A JSON violation event "
                "is required."
            )
        ), 400

    try:
        violation_type = (
            violation_type_for_exam(
                payload.get(
                    "violation_type"
                ),
                exam.monitor_type,
            )
        )

        metadata = sanitize_metadata(
            payload.get("metadata")
        )

        warning, recorded = record_warning(
            submission,
            violation_type,
            metadata,
        )

    except InvalidViolationError:
        return jsonify(
            error=(
                "Invalid supervision event."
            )
        ), 400

    except WarningLimitReachedError:
        return jsonify(
            error=(
                "The warning limit has "
                "already been reached."
            ),
            warning_count=(
                submission.warn_count
            ),
            warning_limit=WARNING_LIMIT,
            warning_limit_reached=True,
        ), 409

    warning_limit_reached = (
        submission.warn_count
        >= WARNING_LIMIT
    )

    if (
        recorded
        and warning_limit_reached
    ):
        finalize_warning_limit(
            submission,
            _supervision_response_payload(
                exam,
                payload.get("responses"),
            ),
        )

    db.session.commit()

    return jsonify(
        recorded=recorded,
        warning_id=warning.id,
        violation_type=(
            warning.violation_type.value
        ),
        message=warning.message,
        occurred_at=(
            warning.occurred_at.isoformat()
        ),
        warning_count=(
            submission.warn_count
        ),
        warning_limit=WARNING_LIMIT,
        warning_limit_reached=(
            warning_limit_reached
        ),
        submitted=(
            submission.is_finalized
        ),
        reason=(
            submission.submission_reason
        ),
    ), 201 if recorded else 200


@candidate_bp.post(
    "/<token>/session/violations/<int:warning_id>/evidence"
)
def upload_violation_evidence(token: str, warning_id: int):
    """Attach one private face-absence clip to its matching warning."""

    exam = _exam_by_token(token)
    submission = _submission_for_request(exam)

    if submission is None:
        return jsonify(
            error="Candidate session required."
        ), 403

    warning = db.session.scalar(
        select(WarningLog)
        .where(
            WarningLog.id == warning_id,
            WarningLog.submission_id == submission.id,
            WarningLog.violation_type
            == ViolationType.FACE_NOT_DETECTED,
        )
        .with_for_update()
    )

    if warning is None:
        return jsonify(
            error="Matching face-absence warning not found."
        ), 404

    if warning.evidence_storage_name is not None:
        return jsonify(
            error="Evidence has already been uploaded."
        ), 409

    stored_path = None

    try:
        stored_path = attach_face_absence_evidence(
            warning,
            request.files.get("video"),
            request.form,
        )
        db.session.commit()

    except EvidenceTooLargeError:
        db.session.rollback()
        return jsonify(
            error="The evidence clip is too large."
        ), 413

    except InvalidEvidenceError:
        db.session.rollback()
        return jsonify(
            error="Invalid evidence upload."
        ), 400

    except Exception:
        db.session.rollback()

        if stored_path is not None:
            stored_path.unlink(missing_ok=True)

        raise

    return jsonify(
        evidence_uploaded=True,
        warning_id=warning.id,
        duration_ms=warning.evidence_duration_ms,
    ), 201


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
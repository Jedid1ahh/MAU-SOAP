"""Passwordless Candidate verification routes for one shared examination."""

from __future__ import annotations

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select

from app.extensions import db
from app.models import Exam, VerificationToken

from . import candidate_bp
from .forms import CandidateIdentityForm, OTPVerificationForm
from .services import (
    complete_verification,
    create_verification,
    register_failed_attempt,
    resolve_candidate_session,
    resolve_magic_token,
    send_verification_email,
    verification_is_expired,
    verify_otp,
)
from .session_services import (
    finalize_expired_submission,
    resolve_submission_session,
)


def _exam_by_token(token: str) -> Exam:
    """Resolve a public CSPRNG examination token or return HTTP 404."""

    exam = db.session.scalar(
        select(Exam).where(
            Exam.exam_link_token == token
        )
    )
    if exam is None:
        abort(404)

    return exam


def _pending_session_key(exam: Exam) -> str:
    return f"candidate_pending_verification_{exam.id}"


def _access_session_key(exam: Exam) -> str:
    return f"candidate_access_token_{exam.id}"


def _pending_verification(
    exam: Exam,
) -> VerificationToken | None:
    verification_id = session.get(
        _pending_session_key(exam)
    )

    if not isinstance(verification_id, int):
        return None

    return db.session.scalar(
        select(VerificationToken).where(
            VerificationToken.id == verification_id,
            VerificationToken.exam_id == exam.id,
        )
    )


def _finish_verification(
    exam: Exam,
    verification: VerificationToken,
):
    """Persist verification and establish signed-cookie access."""

    raw_session_token = complete_verification(
        verification
    )
    db.session.commit()

    session.pop(
        _pending_session_key(exam),
        None,
    )
    session[
        _access_session_key(exam)
    ] = raw_session_token
    session.permanent = True

    flash(
        (
            "Email verified. Review the examination "
            "details before starting."
        ),
        "success",
    )

    return redirect(
        url_for(
            "candidate.exam_ready",
            token=exam.exam_link_token,
        )
    )


@candidate_bp.get("/")
def index():
    """Explain Candidate examination-link access."""

    return render_template(
        "placeholder.html",
        page_title="Candidate area",
        message=(
            "Use the secure examination link supplied "
            "by your administrator."
        ),
    )


@candidate_bp.route(
    "/<token>",
    methods=["GET", "POST"],
)
def exam_landing(token: str):
    """Collect Candidate identity and send verification credentials."""

    exam = _exam_by_token(token)

    raw_session_token = session.get(
        _access_session_key(exam)
    )

    active_submission = resolve_submission_session(
        exam,
        (
            raw_session_token
            if isinstance(raw_session_token, str)
            else None
        ),
    )

    if active_submission is not None:
        if (
            active_submission.is_finalized
            or finalize_expired_submission(
                active_submission
            )
        ):
            db.session.commit()

            return redirect(
                url_for(
                    "candidate.submission_received",
                    token=token,
                )
            )

        return redirect(
            url_for(
                "candidate.exam_session",
                token=token,
            )
        )

    active_verification = resolve_candidate_session(
        exam,
        raw_session_token,
    )

    if active_verification is not None:
        return redirect(
            url_for(
                "candidate.exam_ready",
                token=token,
            )
        )

    form = CandidateIdentityForm()

    if form.validate_on_submit():
        (
            raw_otp,
            raw_magic_token,
            verification,
        ) = create_verification(
            exam,
            form.name.data,
            form.email.data,
        )

        try:
            db.session.flush()

            send_verification_email(
                verification,
                raw_otp,
                raw_magic_token,
            )

            db.session.commit()
        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Unable to send Candidate verification email"
            )

            flash(
                (
                    "Verification email could not be sent. "
                    "Please try again."
                ),
                "error",
            )

            return render_template(
                "candidate/exam_landing.html",
                exam=exam,
                form=form,
            )

        session[
            _pending_session_key(exam)
        ] = verification.id

        flash(
            (
                "A verification code and secure link "
                "have been sent."
            ),
            "success",
        )

        return redirect(
            url_for(
                "candidate.verify_otp_code",
                token=token,
            )
        )

    return render_template(
        "candidate/exam_landing.html",
        exam=exam,
        form=form,
    )


@candidate_bp.route(
    "/<token>/verify",
    methods=["GET", "POST"],
)
def verify_otp_code(token: str):
    """Verify the emailed OTP with five-attempt lockout."""

    exam = _exam_by_token(token)
    verification = _pending_verification(exam)

    if verification is None:
        flash(
            (
                "Request a new verification code "
                "to continue."
            ),
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_landing",
                token=token,
            )
        )

    if (
        verification.is_locked
        or verification.verified_at is not None
        or verification_is_expired(verification)
    ):
        session.pop(
            _pending_session_key(exam),
            None,
        )

        flash(
            (
                "That verification request is "
                "no longer valid."
            ),
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_landing",
                token=token,
            )
        )

    form = OTPVerificationForm()

    if request.method == "POST":
        if (
            form.validate()
            and verify_otp(
                verification,
                form.otp.data,
            )
        ):
            return _finish_verification(
                exam,
                verification,
            )

        register_failed_attempt(verification)
        db.session.commit()

        if verification.is_locked:
            session.pop(
                _pending_session_key(exam),
                None,
            )

            flash(
                (
                    "Too many incorrect codes. "
                    "Request a new verification email."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "candidate.exam_landing",
                    token=token,
                )
            )

        remaining_attempts = (
            5 - verification.attempts
        )

        flash(
            (
                f"Incorrect code. {remaining_attempts} "
                "attempt(s) remaining."
            ),
            "error",
        )

    return render_template(
        "candidate/verify_otp.html",
        exam=exam,
        form=form,
        verification=verification,
    )


@candidate_bp.get(
    "/<token>/verify/<magic_token>"
)
def verify_magic_link(
    token: str,
    magic_token: str,
):
    """Verify Candidate identity from the emailed link."""

    exam = _exam_by_token(token)

    verification = resolve_magic_token(
        exam,
        magic_token,
    )

    if verification is None:
        flash(
            (
                "That verification link is invalid "
                "or has expired."
            ),
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_landing",
                token=token,
            )
        )

    return _finish_verification(
        exam,
        verification,
    )


@candidate_bp.get("/<token>/ready")
def exam_ready(token: str):
    """Show the protected pre-examination screen."""

    exam = _exam_by_token(token)

    verification = resolve_candidate_session(
        exam,
        session.get(
            _access_session_key(exam)
        ),
    )

    if verification is None:
        session.pop(
            _access_session_key(exam),
            None,
        )

        flash(
            (
                "Verify your email address before "
                "accessing this examination."
            ),
            "error",
        )

        return redirect(
            url_for(
                "candidate.exam_landing",
                token=token,
            )
        )

    return render_template(
        "candidate/exam_ready.html",
        exam=exam,
        verification=verification,
    )
"""Registration, verification, login, and logout routes."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select

from app.access import portal_endpoint
from app.extensions import bcrypt, db
from app.models import Role, User

from . import accounts_bp
from .forms import (
    AccountLoginForm,
    LecturerRegistrationForm,
    RegistrationForm,
    StudentRegistrationForm,
)
from .services import (
    create_account_verification,
    resolve_account_verification,
    send_account_verification_email,
    utc_now,
)


def _safe_next_url(target: str | None) -> str | None:
    """Allow a local post-login destination and reject external redirects."""

    if not target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    return target


def _register_account(form: RegistrationForm, role: Role):
    """Create one inactive-until-verified institutional account."""

    if form.validate_on_submit():
        email = form.email.data.strip().casefold()
        existing = db.session.scalar(select(User).where(User.email == email))
        if existing is not None:
            form.email.errors.append(
                "An account already exists for this email address."
            )
        else:
            user = User(
                full_name=form.full_name.data.strip(),
                email=email,
                password_hash=bcrypt.generate_password_hash(
                    form.password.data
                ).decode("utf-8"),
                role=role,
            )
            db.session.add(user)
            try:
                db.session.flush()
                raw_token, _ = create_account_verification(user)
                send_account_verification_email(user, raw_token)
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception(
                    "Unable to create or verify institutional account"
                )
                flash(
                    "The account could not be created. Please try again.",
                    "error",
                )
            else:
                session["pending_account_email"] = user.email
                return redirect(url_for("accounts.check_email"))

    return render_template(
        "accounts/register.html",
        form=form,
        role=role,
    )


@accounts_bp.route("/register/lecturer", methods=["GET", "POST"])
def register_lecturer():
    """Register a Lecturer for email verification and Admin approval."""

    if current_user.is_authenticated:
        return redirect(url_for(portal_endpoint(current_user.role)))
    return _register_account(LecturerRegistrationForm(), Role.LECTURER)


@accounts_bp.route("/register/student", methods=["GET", "POST"])
def register_student():
    """Register a Student using the configured student email domain."""

    if current_user.is_authenticated:
        return redirect(url_for(portal_endpoint(current_user.role)))
    return _register_account(StudentRegistrationForm(), Role.STUDENT)


@accounts_bp.get("/check-email")
def check_email():
    """Explain the next step without exposing verification credentials."""

    return render_template(
        "accounts/check_email.html",
        email=session.get("pending_account_email"),
    )


@accounts_bp.get("/verify/<token>")
def verify_email(token: str):
    """Activate a verified Student or queue a verified Lecturer for approval."""

    verification = resolve_account_verification(token)
    if verification is None:
        flash("That verification link is invalid or has expired.", "error")
        return redirect(url_for("accounts.login"))

    now = utc_now()
    user = verification.user
    verification.used_at = now
    user.email_verified_at = now
    if user.role is Role.STUDENT:
        user.approved_at = now
    db.session.commit()

    if user.role is Role.LECTURER:
        flash(
            "Email verified. An Admin must approve your Lecturer account.",
            "success",
        )
    else:
        flash("Email verified. You can now log in.", "success")
    return redirect(url_for("accounts.login"))


@accounts_bp.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate any role and send it to the matching dashboard."""

    if current_user.is_authenticated:
        return redirect(url_for(portal_endpoint(current_user.role)))

    form = AccountLoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().casefold()
        user = db.session.scalar(select(User).where(User.email == email))
        valid_password = user is not None and bcrypt.check_password_hash(
            user.password_hash,
            form.password.data,
        )
        if user is not None and valid_password and user.is_active:
            if not user.is_email_verified:
                flash("Verify your institutional email before logging in.", "error")
            elif not user.is_approved:
                flash("Your Lecturer account is awaiting Admin approval.", "info")
            else:
                login_user(user)
                session.permanent = True
                destination = _safe_next_url(request.args.get("next"))
                return redirect(
                    destination or url_for(portal_endpoint(user.role))
                )
        else:
            flash("Invalid email address or password.", "error")

    return render_template("accounts/login.html", form=form)


@accounts_bp.post("/logout")
def logout():
    """End any authenticated Admin, Lecturer, or Student session."""

    if current_user.is_authenticated:
        logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("accounts.login"))

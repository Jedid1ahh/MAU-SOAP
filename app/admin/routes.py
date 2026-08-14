"""Admin authentication and account-management routes."""

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

from app.extensions import bcrypt, db
from app.models import Exam, PasswordResetToken, User

from . import admin_bp
from .auth import admin_required
from .forms import LoginForm, PasswordResetForm, PasswordResetRequestForm
from .services import (
    create_reset_token,
    resolve_reset_token,
    send_reset_email,
    utc_now,
)


def _safe_next_url(target: str | None) -> str | None:
    """Allow local redirect paths while rejecting external destinations."""

    if not target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    return target


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate the one pre-provisioned Admin account."""

    if current_user.is_authenticated:
        return redirect(url_for("admin.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().casefold()
        user = db.session.scalar(select(User).where(User.email == email))
        password_is_valid = user is not None and bcrypt.check_password_hash(
            user.password_hash,
            form.password.data,
        )

        if user is not None and user.is_active and password_is_valid:
            login_user(user)
            session.permanent = True
            destination = _safe_next_url(request.args.get("next"))
            return redirect(destination or url_for("admin.index"))

        flash("Invalid email address or password.", "error")

    return render_template("admin/login.html", form=form)


@admin_bp.post("/logout")
@admin_required
def logout():
    """Terminate the Admin's authenticated session."""

    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin.login"))


@admin_bp.get("/")
@admin_required
def index():
    """Render the Admin's Phase 4 examination dashboard."""

    exams = db.session.scalars(
        select(Exam)
        .where(Exam.admin_id == current_user.id)
        .order_by(Exam.created_at.desc())
    ).all()

    return render_template("admin/dashboard.html", exams=exams)

@admin_bp.route("/password-reset", methods=["GET", "POST"])
def request_password_reset():
    """Create and email a reset link without disclosing account existence."""

    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        email = form.email.data.strip().casefold()
        user = db.session.scalar(select(User).where(User.email == email))

        if user is not None and user.is_active:
            raw_token, _ = create_reset_token(user)
            try:
                send_reset_email(user, raw_token)
                db.session.commit()
            except (
                Exception
            ):  # pragma: no cover - SMTP failures are environment-specific
                db.session.rollback()
                current_app.logger.exception("Unable to send Admin reset email")

        flash(
            "If that address belongs to the Admin account, a reset link has been sent.",
            "info",
        )
        return redirect(url_for("admin.login"))

    return render_template("admin/request_reset.html", form=form)


@admin_bp.route("/password-reset/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    """Validate a single-use link and update the Admin password."""

    reset_token = resolve_reset_token(token)
    if reset_token is None:
        flash("That password-reset link is invalid or has expired.", "error")
        return redirect(url_for("admin.request_password_reset"))

    form = PasswordResetForm()
    if form.validate_on_submit():
        now = utc_now()
        reset_token.user.password_hash = bcrypt.generate_password_hash(
            form.password.data
        ).decode("utf-8")
        reset_token.used_at = now

        sibling_tokens = db.session.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == reset_token.user_id,
                PasswordResetToken.id != reset_token.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.locked_at.is_(None),
            )
        )
        for sibling_token in sibling_tokens:
            sibling_token.locked_at = now

        db.session.commit()
        if current_user.is_authenticated:
            logout_user()
        flash("Your password has been reset. You can now log in.", "success")
        return redirect(url_for("admin.login"))

    if request.method == "POST":
        reset_token.attempts += 1
        if reset_token.attempts >= 5:
            reset_token.locked_at = utc_now()
            db.session.commit()
            flash("That password-reset link is no longer valid.", "error")
            return redirect(url_for("admin.request_password_reset"))
        db.session.commit()

    return render_template("admin/reset_password.html", form=form)
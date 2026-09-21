"""Admin authentication and account-management routes."""

from __future__ import annotations

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, logout_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import bcrypt, db
from app.models import Course, PasswordResetToken, Role, User

from . import admin_bp
from .auth import admin_required
from .forms import PasswordResetForm, PasswordResetRequestForm
from .services import (
    create_reset_token,
    resolve_reset_token,
    send_reset_email,
    utc_now,
)


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """Serve the unified login handler at the legacy Admin URL."""

    from app.accounts.routes import login as unified_login

    return unified_login()


@admin_bp.post("/logout")
@admin_required
def logout():
    """Terminate the Admin's authenticated session."""

    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("accounts.login"))


@admin_bp.get("/")
@admin_required
def index():
    """Render system account and course-assignment oversight."""

    courses = db.session.scalars(
        select(Course)
        .options(
            selectinload(Course.lecturer),
            selectinload(Course.exams),
            selectinload(Course.enrollments),
        )
        .order_by(Course.code)
    ).all()

    return render_template("admin/dashboard.html", courses=courses)

@admin_bp.route("/password-reset", methods=["GET", "POST"])
def request_password_reset():
    """Create and email a reset link without disclosing account existence."""

    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        email = form.email.data.strip().casefold()
        user = db.session.scalar(
            select(User).where(
                User.email == email,
                User.role == Role.ADMIN,
            )
        )

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
        return redirect(url_for("accounts.login"))

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
        return redirect(url_for("accounts.login"))

    if request.method == "POST":
        reset_token.attempts += 1
        if reset_token.attempts >= 5:
            reset_token.locked_at = utc_now()
            db.session.commit()
            flash("That password-reset link is no longer valid.", "error")
            return redirect(url_for("admin.request_password_reset"))
        db.session.commit()

    return render_template("admin/reset_password.html", form=form)

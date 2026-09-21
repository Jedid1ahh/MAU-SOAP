"""Admin oversight for Lecturer and Student accounts."""

from flask import abort, flash, redirect, render_template, url_for
from sqlalchemy import select

from app.accounts.services import utc_now
from app.extensions import db
from app.models import Role, User

from . import admin_bp
from .auth import admin_required


def _managed_user(user_id: int) -> User:
    """Load a non-Admin account that the Admin may manage."""

    user = db.session.scalar(
        select(User).where(
            User.id == user_id,
            User.role != Role.ADMIN,
        )
    )
    if user is None:
        abort(404)
    return user


@admin_bp.get("/accounts")
@admin_required
def accounts():
    """List Lecturer approval state and registered Students."""

    users = db.session.scalars(
        select(User)
        .where(User.role != Role.ADMIN)
        .order_by(User.role, User.created_at.desc())
    ).all()
    return render_template("admin/accounts.html", users=users)


@admin_bp.post("/accounts/<int:user_id>/approve")
@admin_required
def approve_lecturer(user_id: int):
    """Approve one email-verified Lecturer account."""

    user = _managed_user(user_id)
    if user.role is not Role.LECTURER or not user.is_email_verified:
        abort(400)
    user.approved_at = utc_now()
    db.session.commit()
    flash(f"Lecturer account approved for {user.email}.", "success")
    return redirect(url_for("admin.accounts"))


@admin_bp.post("/accounts/<int:user_id>/toggle-active")
@admin_required
def toggle_account_active(user_id: int):
    """Suspend or restore a non-Admin institutional account."""

    user = _managed_user(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    state = "restored" if user.is_active else "suspended"
    flash(f"Account {state} for {user.email}.", "success")
    return redirect(url_for("admin.accounts"))

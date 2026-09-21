"""Authorization helpers for the preconfigured MAU-SOAP Admin."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from flask import abort, redirect, request, url_for
from flask_login import current_user

from app.models import Role

ViewFunction = TypeVar("ViewFunction", bound=Callable[..., Any])


def admin_required(view: ViewFunction) -> ViewFunction:
    """Protect Admin views with the seeded account's Flask-Login session."""

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not current_user.is_authenticated:
            return redirect(
                url_for(
                    "accounts.login",
                    next=request.full_path.rstrip("?"),
                )
            )
        if current_user.role is not Role.ADMIN or not current_user.can_access_portal:
            abort(403)
        return view(*args, **kwargs)

    return cast(ViewFunction, wrapped)

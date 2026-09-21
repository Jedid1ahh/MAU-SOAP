"""Role-aware authorization helpers shared by authenticated portals."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from flask import abort, redirect, request, url_for
from flask_login import current_user

from app.models import Role

ViewFunction = TypeVar("ViewFunction", bound=Callable[..., Any])


def portal_endpoint(role: Role) -> str:
    """Return the dashboard endpoint for one authenticated role."""

    return {
        Role.ADMIN: "admin.index",
        Role.LECTURER: "lecturer.index",
        Role.STUDENT: "student.index",
    }[role]


def role_required(*allowed_roles: Role) -> Callable[[ViewFunction], ViewFunction]:
    """Require an active, verified account with one of the supplied roles."""

    def decorator(view: ViewFunction) -> ViewFunction:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            if not current_user.is_authenticated:
                return redirect(
                    url_for(
                        "accounts.login",
                        next=request.full_path.rstrip("?"),
                    )
                )
            if current_user.role not in allowed_roles:
                abort(403)
            if not current_user.can_access_portal:
                abort(403)
            return view(*args, **kwargs)

        return cast(ViewFunction, wrapped)

    return decorator

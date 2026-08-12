"""Authorization helpers for the single MAU-SOAP Admin."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from flask_login import login_required

ViewFunction = TypeVar("ViewFunction", bound=Callable[..., Any])


def admin_required(view: ViewFunction) -> ViewFunction:
    """Protect Admin views with the seeded account's Flask-Login session."""

    return cast(ViewFunction, login_required(view))
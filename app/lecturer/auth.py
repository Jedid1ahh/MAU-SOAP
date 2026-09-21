"""Lecturer authorization helper."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from app.access import role_required
from app.models import Role

ViewFunction = TypeVar("ViewFunction", bound=Callable[..., Any])


def lecturer_required(view: ViewFunction) -> ViewFunction:
    """Require an approved, active Lecturer account."""

    return cast(ViewFunction, role_required(Role.LECTURER)(view))

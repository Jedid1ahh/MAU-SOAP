"""Shared Flask extensions.

Extensions are created without an application and bound inside ``create_app``.
This avoids circular imports and allows tests to create independent app objects.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative model base reserved for the Phase 2 schema."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()


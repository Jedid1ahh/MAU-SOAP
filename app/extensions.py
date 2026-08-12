"""Shared Flask extensions.

Extensions are created without an application and bound inside ``create_app``.
This avoids circular imports and allows tests to create independent app objects.
"""

from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative model base with stable Alembic constraint names."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


db = SQLAlchemy(model_class=Base)


def _render_migration_item(type_, item, autogen_context):
    """Render portable JSON correctly in generated Alembic revisions."""

    if type_ != "type" or not isinstance(item, JSON):
        return False

    if autogen_context.dialect.name == "postgresql":
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return "postgresql.JSONB()"

    return "sa.JSON()"


migrate = Migrate(render_item=_render_migration_item)
bcrypt = Bcrypt()
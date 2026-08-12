"""Tests for extension and migration configuration helpers."""

from sqlalchemy import JSON, String

from app.extensions import _render_migration_item


class _AutogenContext:
    def __init__(self, dialect_name):
        self.dialect = type("Dialect", (), {"name": dialect_name})()
        self.imports = set()


def test_migration_renderer_ignores_non_json_types():
    context = _AutogenContext("sqlite")

    assert _render_migration_item("type", String(), context) is False
    assert _render_migration_item("column", JSON(), context) is False


def test_migration_renderer_uses_generic_json_outside_postgresql():
    context = _AutogenContext("mysql")

    assert _render_migration_item("type", JSON(), context) == "sa.JSON()"


def test_migration_renderer_uses_jsonb_on_postgresql():
    context = _AutogenContext("postgresql")

    assert _render_migration_item("type", JSON(), context) == "postgresql.JSONB()"
    assert "from sqlalchemy.dialects import postgresql" in context.imports
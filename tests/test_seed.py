"""Tests for the idempotent Phase 2 seed command."""

from sqlalchemy import func, select

from app.extensions import bcrypt, db
from app.models import Exam, Question, Role, User


def test_seed_creates_admin_and_development_exam(app):
    result = app.test_cli_runner().invoke(args=["seed-db"])

    assert result.exit_code == 0, result.output
    assert db.session.scalar(select(func.count(User.id))) == 1
    assert db.session.scalar(select(func.count(Exam.id))) == 1
    assert db.session.scalar(select(func.count(Question.id))) == 3

    admin = db.session.scalar(select(User))
    assert admin is not None
    assert admin.email == "admin@mau.edu.ng"
    assert bcrypt.check_password_hash(admin.password_hash, "Phase2TestPassword!")


def test_seed_is_idempotent(app):
    runner = app.test_cli_runner()

    first = runner.invoke(args=["seed-db"])
    second = runner.invoke(args=["seed-db"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert db.session.scalar(select(func.count(User.id))) == 1
    assert db.session.scalar(select(func.count(Exam.id))) == 1
    assert db.session.scalar(select(func.count(Question.id))) == 3


def test_seed_rejects_short_admin_password(app):
    app.config["DEFAULT_ADMIN_PASSWORD"] = "too-short"

    result = app.test_cli_runner().invoke(args=["seed-db"])

    assert result.exit_code != 0
    assert "at least 12 characters" in result.output


def test_seed_requires_admin_settings(app):
    app.config["DEFAULT_ADMIN_EMAIL"] = None

    result = app.test_cli_runner().invoke(args=["seed-db"])

    assert result.exit_code != 0
    assert "DEFAULT_ADMIN_EMAIL is required" in result.output


def test_seed_refuses_second_admin(app):
    db.session.add(
        User(
            email="other@mau.edu.ng",
            password_hash="existing-hash",
            role=Role.ADMIN,
        )
    )
    db.session.commit()

    result = app.test_cli_runner().invoke(args=["seed-db"])

    assert result.exit_code != 0
    assert "Refusing to create a second one" in result.output


def test_seed_can_disable_development_exam(app):
    app.config["SEED_DUMMY_EXAM"] = False

    result = app.test_cli_runner().invoke(args=["seed-db"])

    assert result.exit_code == 0, result.output
    assert db.session.scalar(select(func.count(User.id))) == 1
    assert db.session.scalar(select(func.count(Exam.id))) == 0


def test_seed_rolls_back_unexpected_database_error(app, monkeypatch):
    def fail_seed(*_args, **_kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr("app.cli._seed_admin", fail_seed)

    result = app.test_cli_runner().invoke(args=["seed-db"])

    assert result.exit_code != 0
    assert "Database seed failed" in result.output
"""Database initialization commands for MAU-SOAP."""

from __future__ import annotations

import secrets
from decimal import Decimal

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select

from .extensions import bcrypt, db
from .models import (
    Exam,
    MonitorType,
    Question,
    QuestionType,
    ReleaseOption,
    Role,
    User,
)


def _required_seed_setting(name: str) -> str:
    """Read and validate a required seed setting from Flask configuration."""

    value = str(current_app.config.get(name) or "").strip()
    if not value:
        raise click.ClickException(
            f"{name} is required. Add it to .env before running seed-db."
        )
    return value


def _seed_admin(email: str, password: str) -> tuple[User, bool]:
    """Create the one default Admin without changing an existing password."""

    normalized_email = email.casefold()
    admin = db.session.scalar(select(User).where(User.role == Role.ADMIN))

    if admin is not None:
        if admin.email.casefold() != normalized_email:
            raise click.ClickException(
                "A different Admin already exists. Refusing to create a second one."
            )
        return admin, False

    if len(password) < 12:
        raise click.ClickException(
            "DEFAULT_ADMIN_PASSWORD must contain at least 12 characters."
        )

    admin = User(
        email=normalized_email,
        password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
        role=Role.ADMIN,
    )
    db.session.add(admin)
    db.session.flush()
    return admin, True


def _seed_dummy_exam(admin: User) -> tuple[Exam, bool]:
    """Create one stable development exam and three example questions."""

    existing_exam = db.session.scalar(
        select(Exam).where(
            Exam.admin_id == admin.id,
            Exam.course_code == "CSC-DEMO",
            Exam.title == "MAU-SOAP Development Examination",
        )
    )
    if existing_exam is not None:
        return existing_exam, False

    exam = Exam(
        admin=admin,
        title="MAU-SOAP Development Examination",
        course_code="CSC-DEMO",
        course_title="Introduction to Computer Science",
        instructions=(
            "Development data only. Answer every question before submitting."
        ),
        time_limit_minutes=30,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token=secrets.token_urlsafe(32),
    )
    exam.questions.extend(
        [
            Question(
                position=1,
                question_text="Which protocol secures ordinary HTTP traffic?",
                question_type=QuestionType.MCQ,
                options={"A": "FTP", "B": "HTTPS", "C": "SMTP", "D": "SSH"},
                correct_answer="B",
                marks=Decimal("2.00"),
            ),
            Question(
                position=2,
                question_text="What does HTTP stand for?",
                question_type=QuestionType.SHORT_ANSWER,
                correct_answer="Hypertext Transfer Protocol",
                marks=Decimal("3.00"),
                short_answer_case_sensitive=False,
                short_answer_trim_whitespace=True,
            ),
            Question(
                position=3,
                question_text=(
                    "Explain one advantage of server-authoritative exam timing."
                ),
                question_type=QuestionType.OPEN_ENDED,
                correct_answer=None,
                marks=Decimal("5.00"),
            ),
        ]
    )
    db.session.add(exam)
    db.session.flush()
    return exam, True


@click.command("seed-db")
@with_appcontext
def seed_db_command() -> None:
    """Idempotently provision the Admin and optional development exam."""

    email = _required_seed_setting("DEFAULT_ADMIN_EMAIL")
    password = _required_seed_setting("DEFAULT_ADMIN_PASSWORD")

    try:
        admin, admin_created = _seed_admin(email, password)
        exam_created = False

        if current_app.config.get("SEED_DUMMY_EXAM", False):
            _, exam_created = _seed_dummy_exam(admin)

        db.session.commit()
    except click.ClickException:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        raise click.ClickException(f"Database seed failed: {exc}") from exc

    admin_status = "created" if admin_created else "already exists"
    exam_status = "created" if exam_created else "already exists or disabled"
    click.echo(f"Default Admin: {admin_status}.")
    click.echo(f"Development exam: {exam_status}.")

@click.command(
    "cleanup-supervision-evidence"
)
@with_appcontext
def cleanup_supervision_evidence_command() -> None:
    """Delete supervision clips beyond the retention period."""

    from .candidate.evidence_services import (
        purge_expired_evidence,
    )

    try:
        deleted_count = (
            purge_expired_evidence()
        )
        db.session.commit()

    except Exception as exc:
        db.session.rollback()

        raise click.ClickException(
            "Supervision evidence cleanup failed: "
            f"{exc}"
        ) from exc

    click.echo(
        f"Deleted {deleted_count} expired "
        "supervision evidence file(s)."
    )
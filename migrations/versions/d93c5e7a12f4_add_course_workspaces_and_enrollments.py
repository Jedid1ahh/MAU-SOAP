"""Add course workspaces and Student enrollments

Revision ID: d93c5e7a12f4
Revises: b7f4a2c91d3e
Create Date: 2026-09-21 14:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "d93c5e7a12f4"
down_revision = "b7f4a2c91d3e"
branch_labels = None
depends_on = None


def _expand_graded_by_enum() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TYPE graded_by ADD VALUE IF NOT EXISTS 'lecturer'")
    elif dialect in {"mysql", "mariadb"}:
        op.execute(
            "ALTER TABLE answer_grades MODIFY graded_by "
            "ENUM('automatic','admin','lecturer') NULL"
        )
    else:
        with op.batch_alter_table(
            "answer_grades", recreate="always"
        ) as batch_op:
            batch_op.alter_column(
                "graded_by",
                existing_type=sa.Enum(
                    "automatic", "admin", name="graded_by"
                ),
                type_=sa.Enum(
                    "automatic",
                    "admin",
                    "lecturer",
                    name="graded_by",
                    create_constraint=True,
                ),
                existing_nullable=True,
            )


def _contract_graded_by_enum() -> None:
    op.execute(
        sa.text(
            "UPDATE answer_grades SET graded_by = 'admin' "
            "WHERE graded_by = 'lecturer'"
        )
    )
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TYPE graded_by RENAME TO graded_by_with_lecturer")
        op.execute("CREATE TYPE graded_by AS ENUM ('automatic', 'admin')")
        op.execute(
            "ALTER TABLE answer_grades ALTER COLUMN graded_by TYPE graded_by "
            "USING graded_by::text::graded_by"
        )
        op.execute("DROP TYPE graded_by_with_lecturer")
    elif dialect in {"mysql", "mariadb"}:
        op.execute(
            "ALTER TABLE answer_grades MODIFY graded_by "
            "ENUM('automatic','admin') NULL"
        )
    else:
        with op.batch_alter_table(
            "answer_grades", recreate="always"
        ) as batch_op:
            batch_op.alter_column(
                "graded_by",
                existing_type=sa.Enum(
                    "automatic",
                    "admin",
                    "lecturer",
                    name="graded_by",
                ),
                type_=sa.Enum(
                    "automatic",
                    "admin",
                    name="graded_by",
                    create_constraint=True,
                ),
                existing_nullable=True,
            )


def upgrade():
    _expand_graded_by_enum()

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("lecturer_id", sa.Integer(), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"],
            ["users.id"],
            name=op.f("fk_courses_created_by_admin_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lecturer_id"],
            ["users.id"],
            name=op.f("fk_courses_lecturer_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
    )
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_courses_code"), ["code"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_courses_created_by_admin_id"),
            ["created_by_admin_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_courses_lecturer_id"),
            ["lecturer_id"],
            unique=False,
        )

    with op.batch_alter_table("exams", schema=None) as batch_op:
        batch_op.add_column(sa.Column("course_id", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            "INSERT INTO courses "
            "(code, title, description, lecturer_id, created_by_admin_id, "
            "created_at, updated_at) "
            "SELECT course_code, MIN(course_title), NULL, NULL, MIN(admin_id), "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM exams GROUP BY course_code"
        )
    )
    op.execute(
        sa.text(
            "UPDATE exams SET course_id = "
            "(SELECT courses.id FROM courses "
            "WHERE courses.code = exams.course_code)"
        )
    )

    with op.batch_alter_table("exams", schema=None) as batch_op:
        batch_op.alter_column(
            "course_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_exams_course_id_courses"),
            "courses",
            ["course_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            batch_op.f("ix_exams_course_id"), ["course_id"], unique=False
        )

    op.create_table(
        "course_enrollments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("invited_by_lecturer_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "accepted",
                name="enrollment_status",
                create_constraint=True,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_enrollments_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_lecturer_id"],
            ["users.id"],
            name=op.f(
                "fk_course_enrollments_invited_by_lecturer_id_users"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_course_enrollments_student_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_enrollments")),
        sa.UniqueConstraint("course_id", "student_id", name="course_student"),
    )
    with op.batch_alter_table("course_enrollments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_course_enrollments_course_id"),
            ["course_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_course_enrollments_invited_by_lecturer_id"),
            ["invited_by_lecturer_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_course_enrollments_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_course_enrollments_student_id"),
            ["student_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("course_enrollments", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_course_enrollments_student_id")
        )
        batch_op.drop_index(batch_op.f("ix_course_enrollments_status"))
        batch_op.drop_index(
            batch_op.f("ix_course_enrollments_invited_by_lecturer_id")
        )
        batch_op.drop_index(batch_op.f("ix_course_enrollments_course_id"))
    op.drop_table("course_enrollments")

    with op.batch_alter_table("exams", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exams_course_id"))
        batch_op.drop_constraint(
            batch_op.f("fk_exams_course_id_courses"), type_="foreignkey"
        )
        batch_op.drop_column("course_id")

    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_courses_lecturer_id"))
        batch_op.drop_index(
            batch_op.f("ix_courses_created_by_admin_id")
        )
        batch_op.drop_index(batch_op.f("ix_courses_code"))
    op.drop_table("courses")

    _contract_graded_by_enum()

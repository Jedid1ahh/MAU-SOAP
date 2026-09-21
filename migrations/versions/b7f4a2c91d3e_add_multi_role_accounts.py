"""Add Lecturer and Student account roles

Revision ID: b7f4a2c91d3e
Revises: c6a9d4e21f73
Create Date: 2026-09-21 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "b7f4a2c91d3e"
down_revision = "c6a9d4e21f73"
branch_labels = None
depends_on = None


def _expand_role_enum() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'lecturer'")
        op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'student'")
    elif dialect in {"mysql", "mariadb"}:
        op.execute(
            "ALTER TABLE users MODIFY role "
            "ENUM('admin','lecturer','student') "
            "NOT NULL DEFAULT 'admin'"
        )
    else:
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.alter_column(
                "role",
                existing_type=sa.Enum("admin", name="role"),
                type_=sa.Enum(
                    "admin",
                    "lecturer",
                    "student",
                    name="role",
                    create_constraint=True,
                ),
                existing_nullable=False,
                existing_server_default="admin",
            )


def _contract_role_enum() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TYPE role RENAME TO role_with_accounts")
        op.execute("CREATE TYPE role AS ENUM ('admin')")
        op.execute(
            "ALTER TABLE users ALTER COLUMN role TYPE role "
            "USING role::text::role"
        )
        op.execute("DROP TYPE role_with_accounts")
    elif dialect in {"mysql", "mariadb"}:
        op.execute(
            "ALTER TABLE users MODIFY role "
            "ENUM('admin') NOT NULL DEFAULT 'admin'"
        )
    else:
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.alter_column(
                "role",
                existing_type=sa.Enum(
                    "admin",
                    "lecturer",
                    "student",
                    name="role",
                ),
                type_=sa.Enum(
                    "admin",
                    name="role",
                    create_constraint=True,
                ),
                existing_nullable=False,
                existing_server_default="admin",
            )


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_role", type_="unique")
        batch_op.add_column(sa.Column("full_name", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
        )

    _expand_role_enum()

    op.execute(
        sa.text(
            "UPDATE users SET full_name = 'System Administrator', "
            "email_verified_at = CURRENT_TIMESTAMP, "
            "approved_at = CURRENT_TIMESTAMP WHERE role = 'admin'"
        )
    )

    op.create_table(
        "account_verification_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_account_verification_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_account_verification_tokens",
        ),
    )
    with op.batch_alter_table(
        "account_verification_tokens",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            "ix_account_verification_tokens_user_id",
            ["user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_account_verification_tokens_token_hash",
            ["token_hash"],
            unique=True,
        )
        batch_op.create_index(
            "ix_account_verification_tokens_expires_at",
            ["expires_at"],
            unique=False,
        )


def downgrade():
    op.drop_table("account_verification_tokens")
    op.execute(sa.text("DELETE FROM users WHERE role <> 'admin'"))
    _contract_role_enum()

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("approved_at")
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("full_name")
        batch_op.create_unique_constraint("uq_users_role", ["role"])

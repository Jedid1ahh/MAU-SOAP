"""Add protected supervision video evidence metadata

Revision ID: c6a9d4e21f73
Revises: 8f31b0f6c2a4
Create Date: 2026-08-19 11:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "c6a9d4e21f73"
down_revision = "8f31b0f6c2a4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "submissions",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "supervision_consent_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

    with op.batch_alter_table(
        "warning_logs",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "evidence_storage_name",
                sa.String(length=255),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "evidence_content_type",
                sa.String(length=100),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "evidence_byte_size",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "evidence_sha256",
                sa.String(length=64),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "evidence_started_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "evidence_ended_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "evidence_duration_ms",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "evidence_uploaded_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "evidence_deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.create_unique_constraint(
            "uq_warning_logs_evidence_storage_name",
            ["evidence_storage_name"],
        )
        batch_op.create_index(
            batch_op.f(
                "ix_warning_logs_evidence_uploaded_at"
            ),
            ["evidence_uploaded_at"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table(
        "warning_logs",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f(
                "ix_warning_logs_evidence_uploaded_at"
            )
        )
        batch_op.drop_constraint(
            "uq_warning_logs_evidence_storage_name",
            type_="unique",
        )
        batch_op.drop_column("evidence_deleted_at")
        batch_op.drop_column("evidence_uploaded_at")
        batch_op.drop_column("evidence_duration_ms")
        batch_op.drop_column("evidence_ended_at")
        batch_op.drop_column("evidence_started_at")
        batch_op.drop_column("evidence_sha256")
        batch_op.drop_column("evidence_byte_size")
        batch_op.drop_column("evidence_content_type")
        batch_op.drop_column("evidence_storage_name")

    with op.batch_alter_table(
        "submissions",
        schema=None,
    ) as batch_op:
        batch_op.drop_column("supervision_consent_at")
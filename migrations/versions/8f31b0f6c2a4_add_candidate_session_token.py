"""Add Candidate verification session token

Revision ID: 8f31b0f6c2a4
Revises: 4ad1df852a49
Create Date: 2026-08-14 18:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "8f31b0f6c2a4"
down_revision = "4ad1df852a49"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "verification_tokens",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "session_token_hash",
                sa.String(length=64),
                nullable=True,
            )
        )
        batch_op.create_index(
            batch_op.f(
                "ix_verification_tokens_session_token_hash"
            ),
            ["session_token_hash"],
            unique=True,
        )


def downgrade():
    with op.batch_alter_table(
        "verification_tokens",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f(
                "ix_verification_tokens_session_token_hash"
            )
        )
        batch_op.drop_column("session_token_hash")
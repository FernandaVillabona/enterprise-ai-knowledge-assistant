"""message evaluation and feedback

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("evaluation", JSONB(), nullable=True))
    op.add_column("messages", sa.Column("faithfulness_score", sa.Float(), nullable=True))
    op.add_column(
        "messages", sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("messages", sa.Column("feedback_rating", sa.SmallInteger(), nullable=True))
    op.add_column("messages", sa.Column("feedback_comment", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_messages_feedback_rating", "messages", "feedback_rating IN (-1, 1)"
    )
    # Índice parcial: solo indexa las filas marcadas, que son las que se consultan para revisar
    op.create_index(
        "ix_messages_flagged", "messages", ["created_at"], postgresql_where=sa.text("flagged")
    )


def downgrade() -> None:
    op.drop_index("ix_messages_flagged", table_name="messages")
    op.drop_constraint("ck_messages_feedback_rating", "messages", type_="check")
    for column in ("feedback_comment", "feedback_rating", "flagged", "faithfulness_score", "evaluation"):
        op.drop_column("messages", column)

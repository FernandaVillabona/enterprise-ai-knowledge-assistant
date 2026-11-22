"""groups, memberships and document access

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22

Los documentos que ya existían pasan a `restricted` sin grupos: solo los verán los
administradores hasta que se les asigne acceso. Es la opción segura (denegar por
defecto): nunca exponemos de golpe documentos que antes eran solo de admins.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

visibility = sa.Enum("public", "restricted", name="document_visibility")


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_groups",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_user_groups_group_id", "user_groups", ["group_id"])
    op.create_table(
        "document_groups",
        sa.Column(
            "document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_document_groups_group_id", "document_groups", ["group_id"])

    visibility.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "documents",
        sa.Column("visibility", visibility, nullable=False, server_default="restricted"),
    )


def downgrade() -> None:
    op.drop_column("documents", "visibility")
    visibility.drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_document_groups_group_id", table_name="document_groups")
    op.drop_table("document_groups")
    op.drop_index("ix_user_groups_group_id", table_name="user_groups")
    op.drop_table("user_groups")
    op.drop_table("groups")

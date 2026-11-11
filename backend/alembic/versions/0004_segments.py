"""Segments: a topic covered by several stretches of video

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.add_column(sa.Column("segments", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("uncovered", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.drop_column("uncovered")
        batch.drop_column("segments")

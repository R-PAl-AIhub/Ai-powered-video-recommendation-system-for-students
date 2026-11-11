"""Study ranges: where a topic ends inside its video

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("recommendations", "questions"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("end_s", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    for table in ("recommendations", "questions"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("end_s")

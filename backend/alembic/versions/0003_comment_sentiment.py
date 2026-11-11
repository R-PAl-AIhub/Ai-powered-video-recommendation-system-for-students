"""Comment sentiment per video

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("videos") as batch:
        batch.add_column(sa.Column("comment_sentiment", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("videos") as batch:
        batch.drop_column("comment_sentiment")

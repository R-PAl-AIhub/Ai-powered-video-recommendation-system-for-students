"""Study material: document passages with pages, and readings per topic

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(
            sa.Column("source_url", sa.String(1000), nullable=False, server_default="")
        )

    op.create_table(
        "document_passages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_end", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_label", sa.String(40), nullable=False, server_default=""),
        sa.Column("heading", sa.String(300), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column("embedded_with", sa.String(120), nullable=False, server_default=""),
    )
    op.create_index("ix_document_passages_document_id", "document_passages", ["document_id"])
    op.create_index("ix_passage_document_idx", "document_passages", ["document_id", "idx"])

    op.create_table(
        "readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relevance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("first_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_start", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_end", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_label", sa.String(40), nullable=False, server_default=""),
        sa.Column("heading", sa.String(300), nullable=False, server_default=""),
        sa.Column("snippet", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_readings_project_id", "readings", ["project_id"])
    op.create_index("ix_readings_topic_id", "readings", ["topic_id"])
    op.create_index("ix_readings_document_id", "readings", ["document_id"])


def downgrade() -> None:
    op.drop_table("readings")
    op.drop_table("document_passages")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("source_url")

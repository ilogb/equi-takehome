"""initial schema

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _pk() -> sa.Column:
    return sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True)


def _user_id() -> sa.Column:
    return sa.Column("user_id", sa.BigInteger, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)


def _bool(name: str) -> sa.Column:
    return sa.Column(name, sa.Boolean, nullable=False, server_default=sa.text("false"))


def _jsonb(name: str) -> sa.Column:
    return sa.Column(name, pg.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "user",
        _pk(),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("refresh_token_enc", sa.Text),
        _bool("needs_reconnect"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "watched_folder",
        _pk(),
        _user_id(),
        sa.Column("drive_folder_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("page_token", sa.String),
        _jsonb("descendant_ids"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.UniqueConstraint("user_id", name="uq_watched_folder_user"),
    )
    op.create_table(
        "source_file",
        _pk(),
        _user_id(),
        sa.Column("drive_file_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("path", sa.String, nullable=False, server_default=""),
        sa.Column("mime_type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("error", sa.Text),
        _bool("missing_in_drive"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "drive_file_id", name="uq_source_file_user_drive"),
    )
    op.create_table(
        "document",
        _pk(),
        _user_id(),
        sa.Column("source_file_id", sa.BigInteger, sa.ForeignKey("source_file.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("doc_type", sa.String, nullable=False),
        sa.Column("manager", sa.String),
        sa.Column("as_of_date", sa.Date),
        sa.Column("currency", sa.String),
        sa.Column("summary", sa.Text),
        sa.Column("tags", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        _jsonb("funds"),
        _jsonb("page_texts"),
        sa.Column("model", sa.String),
        sa.Column("prompt_version", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "fund",
        _pk(),
        _user_id(),
        sa.Column("canonical_name", sa.String, nullable=False),
        sa.Column("manager", sa.String),
        sa.Column("normalized_key", sa.String, nullable=False),
        sa.UniqueConstraint("user_id", "normalized_key", name="uq_fund_user_key"),
    )
    op.create_table(
        "fund_alias",
        _pk(),
        _user_id(),
        sa.Column("fund_id", sa.BigInteger, sa.ForeignKey("fund.id", ondelete="CASCADE"), nullable=False),
        sa.Column("normalized_key", sa.String, nullable=False),
        sa.UniqueConstraint("user_id", "normalized_key", name="uq_fund_alias_user_key"),
    )
    op.create_table(
        "printed_table",
        _pk(),
        _user_id(),
        sa.Column("document_id", sa.BigInteger, sa.ForeignKey("document.id", ondelete="CASCADE"), nullable=False),
        sa.Column("index", sa.Integer, nullable=False),
        sa.Column("title", sa.String),
        _jsonb("header"),
        _jsonb("rows"),
    )
    op.create_table(
        "common_row",
        _pk(),
        _user_id(),
        sa.Column("document_id", sa.BigInteger, sa.ForeignKey("document.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fund_id", sa.BigInteger, sa.ForeignKey("fund.id", ondelete="SET NULL")),
        sa.Column("entity", sa.String, nullable=False),
        sa.Column("entity_kind", sa.String, nullable=False),
        sa.Column("share_class", sa.String),
        sa.Column("measure", sa.String, nullable=False),
        sa.Column("period_kind", sa.String, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("value", sa.Numeric(24, 10), nullable=False),
        sa.Column("value_as_written", sa.String),
        sa.Column("unit", sa.String),
        sa.Column("currency", sa.String),
        sa.Column("benchmark_name", sa.String),
        sa.Column("table_index", sa.Integer),
        sa.Column("row_index", sa.Integer),
        sa.Column("col_index", sa.Integer),
        _bool("needs_review"),
        sa.Column("review_reason", sa.Text),
        _bool("conflict"),
    )
    op.create_table(
        "chunk",
        _pk(),
        _user_id(),
        sa.Column("document_id", sa.BigInteger, sa.ForeignKey("document.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("tsv", pg.TSVECTOR, sa.Computed("to_tsvector('english', text)", persisted=True)),
        sa.Column("embedding", Vector(1536)),
    )
    op.create_table(
        "job",
        _pk(),
        _user_id(),
        sa.Column("source_file_id", sa.BigInteger, sa.ForeignKey("source_file.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        _bool("force"),
    )

    for table in ("watched_folder", "source_file", "document", "fund", "fund_alias", "printed_table", "common_row", "chunk", "job"):
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
    op.create_index("ix_fund_alias_fund_id", "fund_alias", ["fund_id"])
    op.create_index("ix_printed_table_document_id", "printed_table", ["document_id"])
    op.create_index("ix_common_row_document_id", "common_row", ["document_id"])
    op.create_index("ix_common_row_fund_id", "common_row", ["fund_id"])
    op.create_index("ix_chunk_document_id", "chunk", ["document_id"])
    op.create_index("ix_job_source_file_id", "job", ["source_file_id"])
    op.create_index("ix_common_row_user_measure_period_end", "common_row", ["user_id", "measure", "period_end"])
    op.create_index("ix_chunk_tsv", "chunk", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "chunk",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    for table in ("job", "chunk", "common_row", "printed_table", "fund_alias", "fund", "document", "source_file", "watched_folder", "user"):
        op.drop_table(table)

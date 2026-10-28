import enum
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIMS = 1536


class FileStatus(enum.StrEnum):
    queued = "queued"
    processing = "processing"
    done = "done"
    needs_review = "needs_review"
    failed = "failed"
    unsupported = "unsupported"
    scanned_no_text = "scanned_no_text"


class DocType(enum.StrEnum):
    factsheet = "factsheet"
    performance_report = "performance_report"
    statement = "statement"
    investor_letter = "investor_letter"
    other = "other"


class Measure(enum.StrEnum):
    return_ = "return"
    benchmark_return = "benchmark_return"
    aum = "aum"
    nav = "nav"
    account_value = "account_value"
    account_return = "account_return"


class PeriodKind(enum.StrEnum):
    month = "month"
    qtd = "qtd"
    ytd = "ytd"
    y1 = "1y"
    y3 = "3y"
    y5 = "5y"
    itd = "itd"
    other = "other"


class EntityKind(enum.StrEnum):
    fund = "fund"
    account = "account"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class ChunkKind(enum.StrEnum):
    page = "page"
    table = "table"
    card = "card"


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[int]:
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)


def _user_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = _pk()
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    needs_reconnect: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = _now()


class WatchedFolder(Base):
    __tablename__ = "watched_folder"
    __table_args__ = (UniqueConstraint("user_id", name="uq_watched_folder_user"),)
    id: Mapped[int] = _pk()
    user_id: Mapped[int] = _user_fk()
    drive_folder_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    page_token: Mapped[str | None] = mapped_column(String)
    descendant_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class SourceFile(Base):
    __tablename__ = "source_file"
    __table_args__ = (UniqueConstraint("user_id", "drive_file_id", name="uq_source_file_user_drive"),)
    id: Mapped[int] = _pk()
    user_id: Mapped[int] = _user_fk()
    drive_file_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=FileStatus.queued.value)
    error: Mapped[str | None] = mapped_column(Text)
    missing_in_drive: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = _now()


class Document(Base):
    __tablename__ = "document"
    id: Mapped[int] = _pk()
    user_id: Mapped[int] = _user_fk()
    source_file_id: Mapped[int] = mapped_column(
        ForeignKey("source_file.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String, nullable=False, default=DocType.other.value)
    manager: Mapped[str | None] = mapped_column(String)
    as_of_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    funds: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    page_texts: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    model: Mapped[str | None] = mapped_column(String)
    prompt_version: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = _now()


class Fund(Base):
    __tablename__ = "fund"
    __table_args__ = (UniqueConstraint("user_id", "normalized_key", name="uq_fund_user_key"),)
    id: Mapped[int] = _pk()
    user_id: Mapped[int] = _user_fk()
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    manager: Mapped[str | None] = mapped_column(String)
    normalized_key: Mapped[str] = mapped_column(String, nullable=False)


class FundAlias(Base):
    __tablename__ = "fund_alias"
    __table_args__ = (UniqueConstraint("user_id", "normalized_key", name="uq_fund_alias_user_key"),)
    id: Mapped[int] = _pk()
    user_id: Mapped[int] = _user_fk()
    fund_id: Mapped[int] = mapped_column(ForeignKey("fund.id", ondelete="CASCADE"), nullable=False, index=True)
    normalized_key: Mapped[str] = mapped_column(String, nullable=False)


class PrintedTable(Base):
    __tablename__ = "printed_table"
    id: Mapped[int] = _pk()
    user_id: Mapped[int] = _user_fk()
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    header: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    rows: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")


class CommonRow(Base):
    __tablename__ = "common_row"
    __table_args__ = (Index("ix_common_row_user_measure_period_end", "user_id", "measure", "period_end"),)
    id: Mapped[int] = _pk()
    user_id: Mapped[int] = _user_fk()
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fund_id: Mapped[int | None] = mapped_column(ForeignKey("fund.id", ondelete="SET NULL"), index=True)
    entity: Mapped[str] = mapped_column(String, nullable=False)
    entity_kind: Mapped[str] = mapped_column(String, nullable=False, default=EntityKind.fund.value)
    share_class: Mapped[str | None] = mapped_column(String)
    measure: Mapped[str] = mapped_column(String, nullable=False)
    period_kind: Mapped[str] = mapped_column(String, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    value_as_written: Mapped[str | None] = mapped_column(String)
    unit: Mapped[str | None] = mapped_column(String)
    currency: Mapped[str | None] = mapped_column(String)
    benchmark_name: Mapped[str | None] = mapped_column(String)
    table_index: Mapped[int | None] = mapped_column(Integer)
    row_index: Mapped[int | None] = mapped_column(Integer)
    col_index: Mapped[int | None] = mapped_column(Integer)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    review_reason: Mapped[str | None] = mapped_column(Text)
    conflict: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Chunk(Base):
    __tablename__ = "chunk"
    id: Mapped[int] = _pk()
    user_id: Mapped[int] = _user_fk()
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    embedding = mapped_column(Vector(EMBEDDING_DIMS))
    __table_args__ = (
        Index("ix_chunk_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Job(Base):
    __tablename__ = "job"
    id: Mapped[int] = _pk()
    user_id: Mapped[int] = _user_fk()
    source_file_id: Mapped[int] = mapped_column(
        ForeignKey("source_file.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default=JobStatus.queued.value)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    run_after: Mapped[datetime] = _now()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    force: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

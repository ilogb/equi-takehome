import subprocess
import sys
from pathlib import Path

from pgvector.sqlalchemy import Vector

from app import models
from app.models import Base

BACKEND = Path(__file__).resolve().parents[2]

TABLES = {
    "user", "watched_folder", "source_file", "document", "fund", "fund_alias",
    "printed_table", "common_row", "chunk", "job",
}


def test_enum_members():
    assert {m.value for m in models.FileStatus} == {
        "queued", "processing", "done", "needs_review", "failed", "unsupported", "scanned_no_text"}
    assert {m.value for m in models.DocType} == {
        "factsheet", "performance_report", "statement", "investor_letter", "other"}
    assert {m.value for m in models.Measure} == {
        "return", "benchmark_return", "aum", "nav", "account_value", "account_return"}
    assert {m.value for m in models.PeriodKind} == {
        "month", "qtd", "ytd", "1y", "3y", "5y", "itd", "other"}
    assert {m.value for m in models.EntityKind} == {"fund", "account"}
    assert {m.value for m in models.JobStatus} == {"queued", "running", "done", "failed"}
    assert {m.value for m in models.ChunkKind} == {"page", "table", "card"}


def test_metadata_tables_and_user_scoping():
    tables = Base.metadata.tables
    assert set(tables) == TABLES
    for name, table in tables.items():
        if name != "user":
            assert "user_id" in table.c, name


def test_chunk_embedding_is_vector_1536():
    col = Base.metadata.tables["chunk"].c.embedding
    assert isinstance(col.type, Vector)
    assert col.type.dim == 1536
    assert Base.metadata.tables["chunk"].c.tsv.computed is not None


def _unique_sets(table):
    from sqlalchemy import UniqueConstraint
    sets = {tuple(c.name for c in con.columns) for con in table.constraints if isinstance(con, UniqueConstraint)}
    sets |= {(c_.name,) for c_ in table.columns if c_.unique}
    return sets


def test_unique_constraints():
    t = Base.metadata.tables
    assert ("user_id", "drive_file_id") in _unique_sets(t["source_file"])
    assert ("user_id", "normalized_key") in _unique_sets(t["fund"])
    assert ("user_id", "normalized_key") in _unique_sets(t["fund_alias"])
    assert ("source_file_id",) in _unique_sets(t["document"])
    assert ("email",) in _unique_sets(t["user"])


def test_offline_migration_sql():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini",
         "upgrade", "head", "--sql"],
        cwd=BACKEND, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/d"},
    )
    assert result.returncode == 0, result.stderr
    sql = result.stdout
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "vector(1536)" in sql.lower()
    assert "hnsw" in sql
    assert "vector_cosine_ops" in sql
    assert "GENERATED ALWAYS AS (to_tsvector('english', text)) STORED" in sql

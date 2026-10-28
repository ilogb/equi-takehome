"""Find mode: hybrid full-text + vector search fused with reciprocal rank fusion, and similar documents."""

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Hashable

from pgvector.sqlalchemy import Vector
from sqlalchemy import Select, func, select, type_coerce
from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.pipeline.funds import fund_key
from app.models import EMBEDDING_DIMS, Chunk, Document, SourceFile

log = logging.getLogger(__name__)

RRF_K = 60
CANDIDATES = 50  # per ranking, before fusion
MAX_COSINE_DISTANCE = 0.65  # vector hits farther than this are noise; keeps "no results" possible
SNIPPET_CHARS = 240
SIMILAR_POOL = 500


@dataclass(frozen=True)
class SearchHit:
    document_id: int
    file_name: str
    path: str
    doc_type: str
    manager: str | None
    funds: list
    as_of_date: date | None
    tags: list
    snippet: str
    score: float


@dataclass(frozen=True)
class ChunkHit:
    """A fused chunk with the metadata of the document it belongs to."""

    document_id: int
    text: str
    score: float
    file_name: str = ""
    path: str = ""
    doc_type: str = "other"
    manager: str | None = None
    funds: list = field(default_factory=list)
    as_of_date: date | None = None
    tags: list = field(default_factory=list)


# --- pure helpers ---------------------------------------------------------------------


def rrf_fuse(ranked_lists: list[list[Hashable]], k: int = RRF_K) -> list[tuple[Hashable, float]]:
    """Reciprocal rank fusion: score(id) = sum 1/(k + rank), ranks 1-based. Highest first, ties by first sight."""
    scores: dict[Hashable, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])  # sort is stable: insertion order breaks ties


def make_snippet(text: str, q: str = "", limit: int = SNIPPET_CHARS) -> str:
    """Plain text trimmed around the first query-term match; no markup (the web highlights)."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    pos = -1
    for term in re.findall(r"\w{2,}", q.lower()):
        i = flat.lower().find(term)
        if i != -1 and (pos == -1 or i < pos):
            pos = i
    if pos == -1:
        return flat[: limit - 1].rstrip() + "…"
    start = max(0, pos - limit // 3)
    end = min(len(flat), start + limit)
    start = max(0, end - limit)
    return ("…" if start > 0 else "") + flat[start:end].strip() + ("…" if end < len(flat) else "")


def group_by_document(chunk_hits: list[ChunkHit], q: str = "") -> list[SearchHit]:
    """One hit per document; its best chunk gives the snippet and score. Ordered by that score."""
    best: dict[int, ChunkHit] = {}
    for hit in chunk_hits:
        if hit.document_id not in best or hit.score > best[hit.document_id].score:
            best[hit.document_id] = hit
    ordered = sorted(best.values(), key=lambda h: -h.score)
    return [
        SearchHit(
            document_id=h.document_id, file_name=h.file_name, path=h.path, doc_type=h.doc_type,
            manager=h.manager, funds=h.funds or [], as_of_date=h.as_of_date, tags=h.tags or [],
            snippet=make_snippet(h.text, q), score=h.score,
        )
        for h in ordered
    ]  # fmt: skip


@dataclass(frozen=True)
class SimilarCandidate:
    hit: SearchHit
    funds: frozenset[str]
    manager: str | None
    distance: float | None  # cosine distance to the anchor's mean embedding; None when it has no chunks


def _fund_keys(funds: list) -> frozenset[str]:
    """Identity keys of a document's funds; entries are {"name", "share_class"} dicts or plain names."""
    keys = set()
    for f in funds or []:
        name = f.get("name") if isinstance(f, dict) else f
        if isinstance(name, str) and name.strip():
            share_class = (f.get("share_class") or "").strip() if isinstance(f, dict) else ""
            if share_class and name.lower().rstrip().endswith(share_class.lower()):
                name = name.rstrip()[: -len(share_class)].strip() or name  # "Fund T EUR Acc" -> "Fund"
            keys.add(fund_key(name))
    return frozenset(keys)


def _manager_key(manager: str | None) -> str | None:
    return manager.strip().lower() if manager and manager.strip() else None


def order_similar(candidates: list[SimilarCandidate], anchor: SimilarCandidate) -> list[SearchHit]:
    """Same fund or manager first (newest as-of first), then nearest by distance. Excludes the anchor."""
    a_manager = _manager_key(anchor.manager)

    def related(c: SimilarCandidate) -> bool:
        return bool(c.funds & anchor.funds) or (a_manager is not None and _manager_key(c.manager) == a_manager)

    def key(c: SimilarCandidate):
        dist = c.distance if c.distance is not None else float("inf")
        newest = -(c.hit.as_of_date.toordinal()) if c.hit.as_of_date else float("inf")
        return (0, newest, dist) if related(c) else (1, dist, 0)

    rest = [c for c in candidates if c.hit.document_id != anchor.hit.document_id]
    return [c.hit for c in sorted(rest, key=key)]


# --- queries (always scoped by user_id) -----------------------------------------------


def fulltext_query(user_id: int, q: str, n: int = CANDIDATES) -> Select:
    tsq = func.websearch_to_tsquery("english", q)
    return (
        select(Chunk.id)
        .where(Chunk.user_id == user_id, Chunk.tsv.op("@@")(tsq))
        .order_by(func.ts_rank_cd(Chunk.tsv, tsq).desc(), Chunk.id)
        .limit(n)
    )


def vector_query(user_id: int, embedding: list[float], n: int = CANDIDATES) -> Select:
    dist = Chunk.embedding.cosine_distance(embedding)
    return (
        select(Chunk.id)
        .where(Chunk.user_id == user_id, Chunk.embedding.is_not(None), dist < MAX_COSINE_DISTANCE)
        .order_by(dist, Chunk.id)
        .limit(n)
    )


def chunk_hits_query(user_id: int, chunk_ids: list[int]) -> Select:
    return (
        select(Chunk.id, Chunk.document_id, Chunk.text, Document, SourceFile)
        .join(Document, Document.id == Chunk.document_id)
        .join(SourceFile, SourceFile.id == Document.source_file_id)
        .where(Chunk.user_id == user_id, Chunk.id.in_(chunk_ids))
    )


def _search_hit(doc: Document, file: SourceFile, snippet: str, score: float) -> SearchHit:
    return SearchHit(
        document_id=doc.id, file_name=file.name, path=file.path, doc_type=doc.doc_type, manager=doc.manager,
        funds=doc.funds or [], as_of_date=doc.as_of_date, tags=doc.tags or [], snippet=snippet, score=score,
    )  # fmt: skip


# --- public API -----------------------------------------------------------------------


def simple_search(session: Session, user_id: int, q: str, llm: LLMProvider, limit: int = 20) -> list[SearchHit]:
    q = q.strip()
    if not q:
        return []
    text_ids = list(session.scalars(fulltext_query(user_id, q)))
    try:
        embedding = llm.embed([q])[0]
    except Exception:
        log.warning("query embedding failed; falling back to full-text only", exc_info=True)
        vec_ids = []
    else:
        vec_ids = list(session.scalars(vector_query(user_id, embedding)))
    fused = rrf_fuse([text_ids, vec_ids])
    if not fused:
        return []
    scores = dict(fused)
    rows = session.execute(chunk_hits_query(user_id, list(scores))).all()
    hits = [
        ChunkHit(
            document_id=r.document_id, text=r.text, score=scores[r.id], file_name=r.SourceFile.name,
            path=r.SourceFile.path, doc_type=r.Document.doc_type, manager=r.Document.manager,
            funds=r.Document.funds or [], as_of_date=r.Document.as_of_date, tags=r.Document.tags or [],
        )
        for r in rows
    ]  # fmt: skip
    return group_by_document(hits, q)[:limit]


def similar_candidates_query(user_id: int, document_id: int) -> Select:
    mean = (
        select(Chunk.document_id.label("document_id"), type_coerce(func.avg(Chunk.embedding), Vector(EMBEDDING_DIMS)).label("mean"))
        .where(Chunk.user_id == user_id, Chunk.embedding.is_not(None))
        .group_by(Chunk.document_id)
        .subquery()
    )
    anchor_mean = select(mean.c.mean).where(mean.c.document_id == document_id).scalar_subquery()
    return (
        select(Document, SourceFile, mean.c.mean.cosine_distance(anchor_mean).label("distance"))
        .join(SourceFile, SourceFile.id == Document.source_file_id)
        .outerjoin(mean, mean.c.document_id == Document.id)
        .where(Document.user_id == user_id)
        .order_by(mean.c.mean.cosine_distance(anchor_mean).asc().nulls_last(), Document.id)
        .limit(SIMILAR_POOL)
    )


def similar_documents(session: Session, user_id: int, document_id: int, limit: int = 5) -> list[SearchHit]:
    rows = session.execute(similar_candidates_query(user_id, document_id)).all()
    candidates: list[SimilarCandidate] = []
    anchor: SimilarCandidate | None = None
    for doc, file, distance in rows:
        dist = float(distance) if distance is not None else None
        cand = SimilarCandidate(
            hit=_search_hit(doc, file, make_snippet(doc.summary or ""), 0.0 if dist is None else 1.0 - dist),
            funds=_fund_keys(doc.funds), manager=doc.manager, distance=dist,
        )  # fmt: skip
        candidates.append(cand)
        if doc.id == document_id:
            anchor = cand
    if anchor is None:
        anchor_row = session.execute(
            select(Document, SourceFile)
            .join(SourceFile, SourceFile.id == Document.source_file_id)
            .where(Document.id == document_id, Document.user_id == user_id)
        ).first()
        if anchor_row is None:
            return []
        doc, file = anchor_row
        anchor = SimilarCandidate(_search_hit(doc, file, "", 0.0), _fund_keys(doc.funds), doc.manager, None)
    return order_similar(candidates, anchor)[:limit]

from datetime import date

from sqlalchemy.dialects import postgresql

from app.search.service import (
    ChunkHit,
    SearchHit,
    SimilarCandidate,
    chunk_hits_query,
    fulltext_query,
    group_by_document,
    make_snippet,
    order_similar,
    rrf_fuse,
    similar_candidates_query,
    vector_query,
)


def sql(stmt) -> str:
    """Compiled SQL with the user id bound inline (other binds, e.g. regconfig, stay as parameters)."""
    c = stmt.compile(dialect=postgresql.dialect())
    text = str(c)
    for name, value in c.params.items():
        if name.startswith("user_id") or name.startswith("document_id"):
            text = text.replace(f"%({name})s", str(value))
    return text


def test_rrf_fuse_rewards_agreement():
    fused = rrf_fuse([[1, 2, 3], [3, 1, 4]])
    assert [i for i, _ in fused] == [1, 3, 2, 4]
    assert dict(fused)[1] == 1 / 61 + 1 / 62
    assert rrf_fuse([]) == [] and rrf_fuse([[], []]) == []


def test_rrf_fuse_single_list_keeps_order():
    assert [i for i, _ in rrf_fuse([[9, 8, 7]])] == [9, 8, 7]


def test_group_by_document_best_chunk_gives_snippet():
    hits = [
        ChunkHit(1, "weak chunk", 0.01, file_name="a.pdf"),
        ChunkHit(2, "Terry Smith runs it", 0.03, file_name="b.pdf"),
        ChunkHit(1, "strong chunk", 0.02, file_name="a.pdf"),
    ]
    out = group_by_document(hits)
    assert [h.document_id for h in out] == [2, 1]
    assert out[1].snippet == "strong chunk" and out[1].score == 0.02


def test_snippet_trims_around_first_match_plain_text():
    text = "x " * 300 + "Terry Smith manages Fundsmith " + "y " * 300
    s = make_snippet(text, "terry smith")
    assert "Terry Smith" in s and len(s) <= 242 and "<" not in s
    assert make_snippet("short text", "x") == "short text"
    assert len(make_snippet("a " * 500, "zzz")) <= 241


def _cand(i, funds=(), manager=None, as_of=None, dist=None):
    hit = SearchHit(i, f"{i}.pdf", "", "factsheet", manager, list(funds), as_of, [], "", 0.0)
    return SimilarCandidate(hit, frozenset(f.lower() for f in funds), manager, dist)


def test_order_similar_related_first_newest_then_distance():
    anchor = _cand(1, ["Fundsmith Equity"], "Fundsmith", date(2026, 1, 31), 0.0)
    cands = [
        anchor,
        _cand(2, ["Other"], "Other LLP", date(2026, 9, 30), 0.1),
        _cand(3, ["Fundsmith Equity"], "Fundsmith", date(2026, 8, 31), 0.4),
        _cand(4, [], "FUNDSMITH", date(2026, 3, 31), 0.5),
        _cand(5, ["Third"], "Third", None, 0.05),
    ]
    assert [h.document_id for h in order_similar(cands, anchor)] == [3, 4, 5, 2]


def test_order_similar_no_chunks_last_and_no_manager_match_on_none():
    anchor = _cand(1, [], None, None, 0.0)
    cands = [anchor, _cand(2, [], None, None, None), _cand(3, [], None, None, 0.3)]
    assert [h.document_id for h in order_similar(cands, anchor)] == [3, 2]


def test_queries_always_scoped_to_user():
    assert "chunk.user_id = 7" in sql(fulltext_query(7, "terry smith"))
    assert "websearch_to_tsquery" in sql(fulltext_query(7, "terry smith"))
    assert "chunk.user_id = 7" in sql(vector_query(7, [0.1] * 3))
    assert "<=>" in sql(vector_query(7, [0.1] * 3))
    assert "chunk.user_id = 7" in sql(chunk_hits_query(7, [1, 2]))
    s = sql(similar_candidates_query(7, 3))
    assert "chunk.user_id = 7" in s and "document.user_id = 7" in s

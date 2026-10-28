"""Find mode: hybrid search over document text, plus documents similar to the top hit."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db import get_session
from app.llm.base import LLMProvider
from app.models import User
from app.search.service import SearchHit, similar_documents, simple_search

router = APIRouter(prefix="/api")


def get_llm(request: Request) -> LLMProvider:
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        from app.llm.openai_provider import OpenAIProvider

        llm = request.app.state.llm = OpenAIProvider(request.app.state.settings)
    return llm


def hit_json(h: SearchHit) -> dict:
    return asdict(h)


@router.get("/search", tags=["analyze"], operation_id="search_documents")
def search_documents(
    q: str = Query(min_length=1),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
    llm: LLMProvider = Depends(get_llm),
) -> dict:
    """Find documents by words or meaning (full-text plus semantic search). Returns one hit per document with a
    text snippet, and documents similar to the best hit."""
    hits = simple_search(session, user.id, q, llm, limit)
    similar = similar_documents(session, user.id, hits[0].document_id) if hits else []
    return {"hits": [hit_json(h) for h in hits], "similar_for_first": [hit_json(h) for h in similar]}

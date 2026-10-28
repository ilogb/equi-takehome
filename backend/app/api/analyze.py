"""Analyze mode: answer a question across the extracted data, with an optional table and sources."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analyze.loop import AnalyzeAnswer, answer_question
from app.api.search import get_llm
from app.auth.deps import current_user
from app.db import get_session
from app.llm.base import LLMProvider
from app.models import User

router = APIRouter(prefix="/api")


class AnalyzeQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/analyze", tags=["analyze"], operation_id="analyze")
async def analyze(
    body: AnalyzeQuestion,
    request: Request,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
    llm: LLMProvider = Depends(get_llm),
) -> AnalyzeAnswer:
    """Answer a plain-English question using the read API as tools (at most 5 calls), as the signed-in user."""
    return await answer_question(request.app, session, user, body.question, llm)

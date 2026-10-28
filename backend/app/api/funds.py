"""Funds seen across the user's documents."""

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db import get_session
from app.models import CommonRow, Fund, User

router = APIRouter(prefix="/api")


def funds_query(user_id: int) -> Select:
    return (
        select(
            Fund.id,
            Fund.canonical_name,
            Fund.manager,
            func.coalesce(
                func.array_agg(CommonRow.share_class.distinct()).filter(CommonRow.share_class.is_not(None)),
                literal_column("ARRAY[]::text[]"),
            ).label("share_classes"),
            func.count(CommonRow.document_id.distinct()).label("documents"),
        )
        .select_from(Fund)
        .outerjoin(CommonRow, (CommonRow.fund_id == Fund.id) & (CommonRow.user_id == user_id))
        .where(Fund.user_id == user_id)
        .group_by(Fund.id)
        .order_by(Fund.canonical_name, Fund.id)
    )


@router.get("/funds", tags=["analyze"], operation_id="list_funds")
def list_funds(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[dict]:
    """List the funds found in the user's documents, with manager, share classes and document count."""
    return [
        {
            "id": r.id,
            "name": r.canonical_name,
            "manager": r.manager,
            "share_classes": sorted(r.share_classes or []),
            "documents": r.documents,
        }
        for r in session.execute(funds_query(user.id)).all()
    ]

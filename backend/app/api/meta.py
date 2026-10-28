"""What data exists: measures, period kinds, date span, managers."""

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db import get_session
from app.models import CommonRow, Document, User

router = APIRouter(prefix="/api")


def meta_span_query(user_id: int) -> Select:
    return select(func.min(CommonRow.period_end), func.max(CommonRow.period_end)).where(
        CommonRow.user_id == user_id
    )


@router.get("/meta", tags=["analyze"], operation_id="describe_data")
def describe_data(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    """Describe what is in the user's data: measures, period kinds, the period_end range and managers."""
    measures = session.scalars(
        select(CommonRow.measure).where(CommonRow.user_id == user.id).distinct().order_by(CommonRow.measure)
    ).all()
    kinds = session.scalars(
        select(CommonRow.period_kind)
        .where(CommonRow.user_id == user.id)
        .distinct()
        .order_by(CommonRow.period_kind)
    ).all()
    low, high = session.execute(meta_span_query(user.id)).one()
    managers = session.scalars(
        select(Document.manager)
        .where(Document.user_id == user.id, Document.manager.is_not(None))
        .distinct()
        .order_by(Document.manager)
    ).all()
    return {
        "measures": list(measures),
        "period_kinds": list(kinds),
        "min_period_end": low,
        "max_period_end": high,
        "managers": list(managers),
    }

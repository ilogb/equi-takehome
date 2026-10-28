"""Fund identity: one fund per user across spelling variants of its name."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fund, FundAlias

_DROP_TOKENS = {"fund", "lp", "ltd", "limited", "inc", "plc", "sicav", "the"}
_JOINERS = re.compile(r"[-_/]")
_NON_WORD = re.compile(r"[^a-z0-9\s]")


def normalize_entity(name: str) -> str:
    """Reduce a fund/manager name to a spelling-insensitive key."""
    text = name.lower().replace("&", " and ")
    text = _JOINERS.sub(" ", text)
    text = _NON_WORD.sub("", text)  # "l.p." -> "lp"
    tokens = text.split()
    kept: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "l" and i + 1 < len(tokens) and tokens[i + 1] == "p":
            i += 2  # "l p"
            continue
        if tokens[i] not in _DROP_TOKENS:
            kept.append(tokens[i])
        i += 1
    return " ".join(kept)


def decide_fund(key: str, alias_map: dict[str, int]) -> int | None:
    """Existing fund id for a normalized key, or None meaning "create"."""
    return alias_map.get(key)


def resolve_fund(session: Session, user_id: int, name: str, manager: str | None) -> Fund:
    """Find the user's fund by alias, or create the fund and its alias."""
    key = normalize_entity(name)
    alias_map = dict(
        session.execute(
            select(FundAlias.normalized_key, FundAlias.fund_id).where(FundAlias.user_id == user_id)
        ).all()
    )
    fund_id = decide_fund(key, alias_map)
    if fund_id is not None:
        return session.get(Fund, fund_id)
    fund = Fund(user_id=user_id, canonical_name=name, manager=manager, normalized_key=key)
    session.add(fund)
    session.flush()
    session.add(FundAlias(user_id=user_id, fund_id=fund.id, normalized_key=key))
    session.flush()
    return fund


def known_fund_names(session: Session, user_id: int) -> list[str]:
    """Canonical names of the user's funds, for prompting the extractor."""
    return list(
        session.scalars(
            select(Fund.canonical_name).where(Fund.user_id == user_id).order_by(Fund.canonical_name)
        )
    )

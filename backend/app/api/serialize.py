"""JSON serialisation helpers shared by the read API."""

from decimal import Decimal


def dec_str(v: Decimal | None) -> str | None:
    """Canonical decimal string: fixed-point, no trailing zeros, never an exponent, no "-0"."""
    if v is None:
        return None
    text = format(v, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-0", "-"):
        return "0"
    return text

"""Display formatting. Values arrive from the API as strings (decimals) and ISO dates."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_currency = "$"


def set_currency(symbol: str) -> None:
    global _currency
    _currency = symbol or ""


def currency() -> str:
    return _currency


def dec(value) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else "0"))
    except InvalidOperation:
        return Decimal(0)


def money(value) -> str:
    v = dec(value)
    return f"{'-' if v < 0 else ''}{_currency}{abs(v):,.2f}"


def qty(value) -> str:
    v = dec(value).normalize()
    return f"{v:,f}" if v == v.to_integral() else f"{v:,f}".rstrip("0").rstrip(".")


def signed(value) -> str:
    v = dec(value)
    return ("+" if v > 0 else "") + qty(v)


def day(value) -> str:
    if not value:
        return ""
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(value)


def when(value) -> str:
    """ISO timestamp (UTC) → local date and time."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value)).astimezone().strftime("%d %b %Y %H:%M")
    except ValueError:
        return str(value)


def compact_money(value) -> str:
    v = float(dec(value))
    for limit, suffix in ((1e6, "M"), (1e3, "k")):
        if abs(v) >= limit:
            return f"{_currency}{v / limit:.1f}{suffix}".replace(".0" + suffix, suffix)
    return f"{_currency}{v:,.0f}"

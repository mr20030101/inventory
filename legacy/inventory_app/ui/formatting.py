"""Display formatting shared by every view."""
from __future__ import annotations

_currency = "$"


def set_currency(symbol: str) -> None:
    global _currency
    _currency = symbol


def currency() -> str:
    return _currency


def money(value) -> str:
    value = float(value or 0)
    sign = "-" if value < 0 else ""
    return f"{sign}{_currency}{abs(value):,.2f}"


def qty(value) -> str:
    return f"{int(value or 0):,}"


def signed(value) -> str:
    return f"{int(value or 0):+,}"


def timestamp(value) -> str:
    return str(value)[:16]

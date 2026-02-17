"""Shared financial calculation utilities."""

from decimal import Decimal


def calculate_uitnutting(
    budget: Decimal,
    gerealiseerd: Decimal,
) -> float | None:
    """Calculate utilization percentage from budget and realized spending.

    Returns None if budget is zero or negative.
    """
    if budget and budget > 0:
        return float(gerealiseerd / budget * 100)
    return None

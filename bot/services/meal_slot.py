"""Map the time of a message to a meal slot."""
from __future__ import annotations

from datetime import datetime

SLOTS_RU = {
    "breakfast": "завтрак",
    "lunch": "обед",
    "dinner": "ужин",
    "snack": "перекус",
}


def meal_slot(dt: datetime) -> str:
    h = dt.hour
    if 5 <= h < 11:
        return "breakfast"
    if 11 <= h < 16:
        return "lunch"
    if 16 <= h < 22:
        return "dinner"
    return "snack"

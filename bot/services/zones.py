"""Red/Yellow/Green/Gray zoning for meals and whole days.

Grounded in three nutrition systems:
- Noom color system  -> calorie density (kcal/g) drives green vs yellow vs orange.
- UK FSA traffic light -> per-100g fat/satfat/sugar/salt thresholds.
- NOVA -> ultra-processed (group 4) foods are a red signal.

The per-meal colour (`health_score`) is decided by the vision model using a rubric
built from the above (see bot/llm/prompts.py). This module aggregates those
per-meal colours into ONE colour per day, weighted by calories, plus a gray
"no food logged" state.
"""
from __future__ import annotations

ZONE_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⚪"}
ZONE_RU = {"green": "зелёная", "yellow": "жёлтая", "red": "красная", "gray": "серая"}

_SCORE = {"green": 1.0, "yellow": 0.0, "red": -1.0}


def meal_kcal_mid(meal) -> float:
    if meal.kcal_min and meal.kcal_max:
        return (meal.kcal_min + meal.kcal_max) / 2
    return float(meal.kcal_min or meal.kcal_max or 0)


def day_total_kcal(meals) -> tuple[int, int]:
    lo = sum(m.kcal_min or 0 for m in meals)
    hi = sum(m.kcal_max or 0 for m in meals)
    return lo, hi


def day_zone(meals) -> str:
    """Aggregate a day's meals into one zone, weighted by calories.

    No meals -> 'gray'. A big red meal outweighs a small green snack because the
    average is weighted by each meal's calories.
    """
    if not meals:
        return "gray"
    num = den = 0.0
    for m in meals:
        score = _SCORE.get(m.health_score)
        if score is None:
            continue
        weight = meal_kcal_mid(m) or 1.0
        num += score * weight
        den += weight
    if den == 0:
        return "yellow"  # had food but no usable scores
    avg = num / den
    if avg > 0.34:
        return "green"
    if avg < -0.34:
        return "red"
    return "yellow"

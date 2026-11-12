"""Weighted scoring for neighborhoods and for individual apartments."""

from typing import Dict, List, Tuple

from .criteria import SCORECARD_LABELS, SCORECARD_WEIGHTS, VERDICT_BANDS

# The findings schema names ratings from a neighborhood's point of view; the
# scorecard names the same criteria from an apartment's. Same weights either way.
RATING_TO_CRITERION = {
    "internet": "wifi",
    "cafe_access": "cafe",
    "fitness_access": "fitness",
    "vibe": "vibe",
    "furnished_stock": "furnished",
    "price_value": "price",
    "quiet": "quiet",
    "safety": "safety",
}


def clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def weighted_score(scores: Dict[str, float]) -> float:
    """Turn per-criterion 0-10 scores into a 0-100 weighted total."""
    total = 0.0
    for criterion, weight in SCORECARD_WEIGHTS.items():
        total += clamp(float(scores.get(criterion, 0))) / 10.0 * weight
    return round(total, 1)


def neighborhood_fit(ratings: Dict[str, float]) -> float:
    """Score a neighborhood from the ratings in the findings schema."""
    mapped = {
        criterion: ratings.get(rating_key, 0)
        for rating_key, criterion in RATING_TO_CRITERION.items()
    }
    return weighted_score(mapped)


def verdict(score: float) -> str:
    for threshold, label in VERDICT_BANDS:
        if score >= threshold:
            return label
    return "PASS"


def breakdown(scores: Dict[str, float]) -> List[Tuple[str, str, float, int, float]]:
    """Per-criterion rows: (key, label, raw 0-10, weight, points earned)."""
    rows = []
    for criterion, weight in SCORECARD_WEIGHTS.items():
        raw = clamp(float(scores.get(criterion, 0)))
        rows.append((criterion, SCORECARD_LABELS[criterion], raw, weight, round(raw / 10.0 * weight, 1)))
    return rows


def weakest(scores: Dict[str, float], count: int = 3) -> List[Tuple[str, float, int]]:
    """The criteria costing the most points, worst first — where to push back."""
    losses = []
    for criterion, weight in SCORECARD_WEIGHTS.items():
        raw = clamp(float(scores.get(criterion, 0)))
        losses.append((SCORECARD_LABELS[criterion], round(weight - raw / 10.0 * weight, 1), weight))
    losses.sort(key=lambda row: row[1], reverse=True)
    return [row for row in losses[:count] if row[1] > 0]

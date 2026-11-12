"""JSON Schema for the structured City Scout findings.

Hand-written rather than generated so it stays inside the subset the Claude API
structured-outputs feature accepts: every object needs `additionalProperties:
false` and a complete `required` list, and numeric/string constraints such as
`minimum` or `maxLength` are not supported. Range checks happen in scoring.py.
"""

from typing import Any, Dict, List, Optional

CONFIDENCE = ["confirmed", "likely", "unverified"]


def _obj(properties: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build an object schema with the strictness the API requires."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required if required is not None else list(properties),
        "properties": properties,
    }


def _nullable(type_name: str) -> Dict[str, Any]:
    return {"anyOf": [{"type": type_name}, {"type": "null"}]}


def _place(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    props: Dict[str, Any] = {
        "name": {"type": "string", "description": "Name in the local script plus a romanised form if they differ."},
        "neighborhood": {"type": "string"},
        "address": {"type": "string", "description": "Street address, or the nearest cross-street / station if no street address exists."},
        "maps_query": {
            "type": "string",
            "description": "Exact text that finds this place on Google Maps, e.g. 'Yaguchi Nichome Park, Ota City, Tokyo'.",
        },
        "walk_minutes": dict(_nullable("integer"), description="Walking minutes from the neighborhood centre. Null if you cannot estimate it honestly."),
        "rating": dict(_nullable("number"), description="Google rating out of 5, or null if unknown."),
        "hours": {"type": "string", "description": "Opening hours, or 'unknown'."},
        "fits": {"type": "string", "description": "Why this specifically meets the criteria. Concrete details, never generic praise."},
        "caveat": {
            "type": "string",
            "description": "The honest downside — crowding, price, distance, unreliable hours. Write 'none found' only if you genuinely found none.",
        },
        "confidence": {
            "type": "string",
            "enum": CONFIDENCE,
            "description": "confirmed = multiple sources or photos verify it; likely = one credible source; unverified = inference worth checking on the ground.",
        },
    }
    if extra:
        props.update(extra)
    return _obj(props)


FITNESS_PLACE = _place(
    {
        "equipment": {
            "type": "array",
            "items": {"type": "string"},
            "description": "What is actually installed: pull-up bars, parallel bars, dip station, rings, running track, calisthenics rig.",
        },
        "has_pullup_bars": {"type": "boolean"},
        "has_parallel_bars": {"type": "boolean"},
        "cost": {"type": "string", "description": "'free' for public parks, otherwise the day/month price in local currency and USD."},
    }
)

CAFE_PLACE = _place(
    {
        "opens_at": {"type": "string", "description": "Opening time, e.g. '07:30'. 'unknown' if not found."},
        "outlets": {"type": "string", "enum": ["at_most_tables", "some", "few_or_none", "unknown"]},
        "laptop_friendly": {
            "type": "string",
            "description": "How welcome a 2-4 hour laptop session is, and any time limit the cafe enforces.",
        },
    }
)

FOOD_PLACE = _place(
    {
        "price_range": {"type": "string", "description": "Typical cost of a meal in local currency and USD."},
        "kind": {"type": "string", "enum": ["local_restaurant", "street_food", "market", "grocery", "convenience_store"]},
    }
)

NEIGHBORHOOD_RATINGS = _obj(
    {
        key: {"type": "integer", "description": "0-10, where 10 fully meets the criterion. Be strict; 5 means mediocre."}
        for key in ["internet", "cafe_access", "fitness_access", "vibe", "furnished_stock", "price_value", "quiet", "safety"]
    }
)

NEIGHBORHOOD = _obj(
    {
        "name": {"type": "string"},
        "verdict": {
            "type": "string",
            "enum": ["sweet_spot", "good", "maybe", "avoid"],
            "description": "sweet_spot = the Hai Chau equivalent for this city.",
        },
        "hai_chau_comparison": {
            "type": "string",
            "description": "Place it on Tam's scale: more local than Hai Chau, about the same, or drifting toward Son Tra. Say which and why.",
        },
        "rent_band_usd": {"type": "string", "description": "Realistic monthly rent range in USD for a furnished 1BR, e.g. '$420-650'."},
        "why": {"type": "string", "description": "What makes this neighborhood work for a working nomad couple."},
        "downsides": {"type": "string", "description": "The honest reasons it might not work. Never leave this empty."},
        "best_for": {"type": "string", "description": "One line: who this neighborhood suits."},
        "ratings": NEIGHBORHOOD_RATINGS,
    }
)

HOUSING_SOURCE = _obj(
    {
        "name": {"type": "string"},
        "kind": {"type": "string", "enum": ["facebook_group", "website", "telegram", "zalo", "line", "agent", "walk_in", "other"]},
        "url": {"type": "string", "description": "URL or search term. Use '' if there is no link."},
        "notes": {"type": "string", "description": "How to actually use it, and what the listings there are like."},
    }
)

HOUSING = _obj(
    {
        "price_bands": {"type": "string", "description": "What the budget realistically buys here, by neighborhood and apartment type."},
        "where_to_look": {"type": "array", "items": HOUSING_SOURCE},
        "lease_norms": {"type": "string", "description": "Typical lease length, deposit, utilities, agent fees, and what a foreigner needs to sign."},
        "negotiation_notes": {"type": "string", "description": "How much room there really is off asking price, and the local etiquette for asking."},
        "red_flags": {"type": "array", "items": {"type": "string"}, "description": "City-specific scams, lease traps, and building problems."},
    }
)

CHECKLIST_ITEM = _obj(
    {
        "phase": {"type": "string", "enum": ["research", "landing", "viewing", "negotiate"]},
        "task": {"type": "string", "description": "City-specific and actionable. Not a restatement of the generic SOP."},
        "why": {"type": "string", "description": "What goes wrong in this city if it is skipped."},
    }
)

FINDINGS_SCHEMA = _obj(
    {
        "city": {"type": "string"},
        "country": {"type": "string"},
        "bottom_line": {
            "type": "string",
            "description": "3-5 sentences: is this city a fit, which neighborhood to target, and the single biggest risk.",
        },
        "best_neighborhood": {"type": "string", "description": "The one neighborhood to target first."},
        "neighborhoods": {"type": "array", "items": NEIGHBORHOOD},
        "fitness": {"type": "array", "items": FITNESS_PLACE},
        "cafes": {"type": "array", "items": CAFE_PLACE},
        "food": {"type": "array", "items": FOOD_PLACE},
        "housing": HOUSING,
        "transit": {"type": "string", "description": "How to get around day to day, typical costs, and whether a scooter is needed."},
        "connectivity": {"type": "string", "description": "Realistic home fibre upload speeds, SIM/eSIM options, and typical monthly cost."},
        "cost_of_living": {"type": "string", "description": "Rough monthly total for a couple living the way the travelers live."},
        "visa_notes": {"type": "string", "description": "Visa options for a US passport holder staying 1-3 months, with the caveat that rules change."},
        "pre_arrival_checklist": {"type": "array", "items": CHECKLIST_ITEM},
        "watch_outs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Blunt warnings: seasons to avoid, noise, pollution, areas to skip, anything that would ruin the stay.",
        },
        "sources": {"type": "array", "items": {"type": "string"}, "description": "URLs actually used, most useful first."},
    }
)

RATING_KEYS = list(NEIGHBORHOOD_RATINGS["properties"])

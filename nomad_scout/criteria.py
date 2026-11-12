"""Our non-negotiable criteria, encoded as data.

This is the single source of truth for what "good" means. Edit here and every
prompt, score, and report picks it up.
"""

from typing import Dict, List

# --- Hard constraints -------------------------------------------------------

BUDGET_USD = 800  # per month, fully furnished

REFERENCE_SCALE = {
    "perfect": "Da Nang, Hai Chau district — real residential life, expat-adjacent, not a bubble",
    "slightly_too_local": "Da Nang, Thanh Khe — little English, thin cafe/gym options",
    "borderline_touristy": "Da Nang, Son Tra — beachfront, tourist pricing creeping in",
}

NON_NEGOTIABLES: Dict[str, List[str]] = {
    "neighborhood": [
        "Local but not too local — real residential life, not a tourist trap",
        "Expat-adjacent without being an expat bubble",
        "Benchmark against the Hai Chau / Thanh Khe / Son Tra scale",
    ],
    "housing": [
        "Under ${budget}/month USD, fully furnished".format(budget=BUDGET_USD),
        "Move-in ready: AC, washing machine, kitchen, TV",
        "WiFi 30+ Mbps upload (verify on Fast.com before signing)",
        "Quiet — no nightlife noise, no main-road traffic",
        "Building with elevator preferred; not ground floor",
    ],
    "fitness": [
        "Pull-up bars / horizontal bars within a 15-20 min walk",
        "Parallel bars for dips are a bonus",
        "Outdoor fitness park preferred over an indoor gym for daily use",
        "24hr indoor gym at roughly $3/day is an acceptable supplement",
    ],
    "cafe": [
        "Spacious — big tables, not cramped, not packed",
        "Fast WiFi and power outlets at the tables",
        "Can sit 2-4 hours on one order without pressure",
        "Open by 8-9am",
        "Within a 15 min walk or a short transit hop",
    ],
    "food": [
        "Good local food within walking distance",
        "Not deep tourist-trap pricing",
        "Convenience store (7-Eleven, FamilyMart, Circle K) nearby is a plus",
    ],
}

# --- Apartment scorecard ----------------------------------------------------

# Weights must sum to 100.
SCORECARD_WEIGHTS: Dict[str, int] = {
    "wifi": 20,        # 30+ Mbps upload, measured on Fast.com
    "cafe": 15,        # work cafe within a 5 min walk
    "fitness": 15,     # gym / pull-up bars within 10-15 min
    "vibe": 15,        # neighborhood is local, not touristy
    "furnished": 15,   # AC + washer + kitchen, genuinely move-in ready
    "price": 10,       # value under the budget
    "quiet": 5,        # no nightlife or main-road noise
    "safety": 5,       # safety and building quality
}

SCORECARD_LABELS: Dict[str, str] = {
    "wifi": "WiFi speed 30+ Mbps upload",
    "cafe": "Cafe within 5 min walk",
    "fitness": "Gym / pull-up bars within 10-15 min",
    "vibe": "Neighborhood vibe (local not touristy)",
    "furnished": "Fully furnished (AC + washer + kitchen)",
    "price": "Price value under ${budget}".format(budget=BUDGET_USD),
    "quiet": "Quiet / no noise",
    "safety": "Safety + building quality",
}

VERDICT_BANDS = [
    (80, "BOOK IT"),
    (65, "GOOD"),
    (50, "MAYBE"),
    (0, "PASS"),
]

# --- The housing SOP --------------------------------------------------------

SOP_PHASES = {
    "research": (
        "Phase 1 — Research (before arriving)",
        [
            "Pick target neighborhoods using YouTube vlogs + Google Maps",
            "Open the city Facebook expat housing group and post a want ad immediately",
            "Book a 1-week Airbnb landing pad — never commit long-term without walking the area",
            "Join the local Telegram / LINE / Zalo housing groups",
        ],
    ),
    "landing": (
        "Phase 2 — Scout on the ground (Days 1-3)",
        [
            "Walk the target neighborhood first — find cafe, gym, market proximity on foot",
            "Check Google Maps for a gym within a 10 min walk or bike",
            "Shortlist a maximum of 3-5 apartments",
        ],
    ),
    "viewing": (
        "Phase 3 — View & evaluate",
        [
            "Test WiFi on Fast.com (30+ Mbps upload minimum)",
            "Check water pressure and hot water",
            "Visit the building at 8pm on a weekday to check noise",
            "Confirm AC, washing machine, and kitchen all actually work",
            "Check phone signal inside the unit",
            "Talk to building staff about noise, floods, and insects",
        ],
    ),
    "negotiate": (
        "Phase 4 — Negotiate & book",
        [
            "Never pay asking price — 10-20% off is normal in Asia",
            "Get everything in LINE / WhatsApp in writing",
            "Confirm deposit terms and the early-exit policy",
            "Photo-document every scratch before unpacking",
            "Set a calendar reminder to scout the next city 6 weeks out",
        ],
    ),
}

PHASE_ORDER = ["research", "landing", "viewing", "negotiate"]

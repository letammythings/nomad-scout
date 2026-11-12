"""Optional Google Places enrichment.

Entirely optional. Without GOOGLE_MAPS_API_KEY the tool still works — walk times
and ratings are then the model's estimates. With a key, every place is looked up
on Google Places so you can see which ones actually exist, what they really rate,
and roughly how far they are from the neighborhood centre.
"""

import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import httpx

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    [
        "places.displayName",
        "places.formattedAddress",
        "places.rating",
        "places.userRatingCount",
        "places.location",
        "places.googleMapsUri",
        "places.businessStatus",
    ]
)

# Straight-line metres per walking minute, with a detour factor for real streets.
WALK_METRES_PER_MIN = 80.0
DETOUR_FACTOR = 1.3


def available() -> bool:
    return bool(os.environ.get("GOOGLE_MAPS_API_KEY"))


def _search(client: httpx.Client, query: str) -> Optional[Dict[str, Any]]:
    try:
        response = client.post(
            SEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": os.environ["GOOGLE_MAPS_API_KEY"],
                "X-Goog-FieldMask": FIELD_MASK,
            },
            json={"textQuery": query, "maxResultCount": 1},
            timeout=20.0,
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    places = response.json().get("places") or []
    return places[0] if places else None


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    radius = 6371000.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def _coords(place: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    location = place.get("location") or {}
    if "latitude" in location and "longitude" in location:
        return (location["latitude"], location["longitude"])
    return None


def enrich(findings: Dict[str, Any], anchor_query: Optional[str] = None, progress: bool = True) -> int:
    """Look every place up on Google Places, in place. Returns how many matched."""
    if not available():
        return 0

    anchor: Optional[Tuple[float, float]] = None
    matched = 0

    with httpx.Client() as client:
        if anchor_query:
            anchor_place = _search(client, anchor_query)
            if anchor_place:
                anchor = _coords(anchor_place)

        for section in ("fitness", "cafes", "food"):
            for place in findings.get(section) or []:
                query = place.get("maps_query") or "{name} {hood}".format(
                    name=place.get("name", ""), hood=place.get("neighborhood", "")
                )
                if progress:
                    sys.stderr.write(".")
                    sys.stderr.flush()

                hit = _search(client, query)
                if not hit:
                    place["verified"] = "not found on Google Maps"
                    continue

                matched += 1
                place["verified"] = "found"
                place["google_name"] = (hit.get("displayName") or {}).get("text")
                place["google_url"] = hit.get("googleMapsUri")
                if hit.get("formattedAddress"):
                    place["address"] = hit["formattedAddress"]
                if hit.get("rating") is not None:
                    place["rating"] = hit["rating"]
                if hit.get("userRatingCount") is not None:
                    place["rating_count"] = hit["userRatingCount"]
                if hit.get("businessStatus") and hit["businessStatus"] != "OPERATIONAL":
                    place["verified"] = hit["businessStatus"].replace("_", " ").lower()

                coords = _coords(hit)
                if anchor and coords:
                    metres = _haversine_m(anchor, coords) * DETOUR_FACTOR
                    place["walk_minutes"] = max(1, int(round(metres / WALK_METRES_PER_MIN)))
                    place["walk_source"] = "estimated from Google Places coordinates"

    if progress:
        sys.stderr.write("\n")
    return matched


def unverified(findings: Dict[str, Any]) -> List[str]:
    """Names of places Google could not find — the ones to check on the ground."""
    missing = []
    for section in ("fitness", "cafes", "food"):
        for place in findings.get(section) or []:
            if place.get("verified") and place["verified"] != "found":
                missing.append("{name} ({state})".format(name=place.get("name", "?"), state=place["verified"]))
    return missing

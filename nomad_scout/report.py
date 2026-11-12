"""Render findings into the markdown City Scout Report."""

import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from . import criteria, scoring

CONFIDENCE_BADGE = {"confirmed": "confirmed", "likely": "likely", "unverified": "UNVERIFIED"}
VERDICT_BADGE = {
    "sweet_spot": "SWEET SPOT",
    "good": "GOOD",
    "maybe": "MAYBE",
    "avoid": "AVOID",
}
VERDICT_ORDER = {"sweet_spot": 0, "good": 1, "maybe": 2, "avoid": 3}


def _cell(value: Any, fallback: str = "—") -> str:
    """Make any value safe to drop into a markdown table cell."""
    if value is None or value == "":
        return fallback
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _maps_link(place: Dict[str, Any]) -> str:
    if place.get("google_url"):
        return "[map]({url})".format(url=place["google_url"])
    query = place.get("maps_query") or place.get("name")
    if not query:
        return "—"
    return "[map](https://www.google.com/maps/search/?api=1&query={q})".format(q=quote_plus(str(query)))


def _walk(place: Dict[str, Any]) -> str:
    minutes = place.get("walk_minutes")
    if minutes is None:
        return "?"
    return "{m} min".format(m=minutes)


def _rating(place: Dict[str, Any]) -> str:
    rating = place.get("rating")
    if rating is None:
        return "—"
    count = place.get("rating_count")
    if count:
        return "{r}★ ({c})".format(r=rating, c=count)
    return "{r}★".format(r=rating)


def _status(place: Dict[str, Any]) -> str:
    verified = place.get("verified")
    confidence = CONFIDENCE_BADGE.get(place.get("confidence", ""), place.get("confidence", "—"))
    if verified == "found":
        return "verified"
    if verified:
        return "NOT FOUND"
    return confidence


def _num(value: float) -> str:
    """Trim a trailing .0 so scores read as 82, not 82.0."""
    return str(int(value)) if float(value).is_integer() else str(round(float(value), 1))


def _section(title: str, body: str) -> str:
    return "## {title}\n\n{body}\n".format(title=title, body=body.strip())


def _fitness_table(places: List[Dict[str, Any]]) -> str:
    if not places:
        return "_No outdoor fitness found that meets the criteria. This is a real problem for this city — treat it as a reason to look elsewhere or plan around an indoor gym._"
    lines = [
        "| Place | Neighborhood | Walk | Pull-up | Dip bars | Cost | Rating | Status | Map |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in places:
        lines.append(
            "| **{name}** | {hood} | {walk} | {pull} | {dip} | {cost} | {rating} | {status} | {map} |".format(
                name=_cell(p.get("name")),
                hood=_cell(p.get("neighborhood")),
                walk=_walk(p),
                pull="yes" if p.get("has_pullup_bars") else "no",
                dip="yes" if p.get("has_parallel_bars") else "no",
                cost=_cell(p.get("cost")),
                rating=_rating(p),
                status=_status(p),
                map=_maps_link(p),
            )
        )
    lines.append("")
    for p in places:
        equipment = ", ".join(p.get("equipment") or []) or "not listed"
        lines.append(
            "- **{name}** — {fits}\n  - Equipment: {equipment}\n  - Address: {address}\n  - Caveat: {caveat}".format(
                name=p.get("name", "?"),
                fits=p.get("fits", ""),
                equipment=equipment,
                address=p.get("address") or "unknown",
                caveat=p.get("caveat") or "none noted",
            )
        )
    return "\n".join(lines)


def _cafe_table(places: List[Dict[str, Any]]) -> str:
    if not places:
        return "_No cafes found that pass the spacious / outlets / long-session test._"
    lines = [
        "| Cafe | Neighborhood | Walk | Opens | Outlets | Rating | Status | Map |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for p in places:
        lines.append(
            "| **{name}** | {hood} | {walk} | {opens} | {outlets} | {rating} | {status} | {map} |".format(
                name=_cell(p.get("name")),
                hood=_cell(p.get("neighborhood")),
                walk=_walk(p),
                opens=_cell(p.get("opens_at")),
                outlets=_cell((p.get("outlets") or "").replace("_", " ")),
                rating=_rating(p),
                status=_status(p),
                map=_maps_link(p),
            )
        )
    lines.append("")
    for p in places:
        lines.append(
            "- **{name}** — {fits}\n  - Long sessions: {laptop}\n  - Hours: {hours}\n  - Caveat: {caveat}".format(
                name=p.get("name", "?"),
                fits=p.get("fits", ""),
                laptop=p.get("laptop_friendly") or "unknown",
                hours=p.get("hours") or "unknown",
                caveat=p.get("caveat") or "none noted",
            )
        )
    return "\n".join(lines)


def _food_table(places: List[Dict[str, Any]]) -> str:
    if not places:
        return "_Nothing specific found. Walk the area and judge it in person._"
    lines = [
        "| Place | Kind | Neighborhood | Walk | Price | Rating | Status | Map |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for p in places:
        lines.append(
            "| **{name}** | {kind} | {hood} | {walk} | {price} | {rating} | {status} | {map} |".format(
                name=_cell(p.get("name")),
                kind=_cell((p.get("kind") or "").replace("_", " ")),
                hood=_cell(p.get("neighborhood")),
                walk=_walk(p),
                price=_cell(p.get("price_range")),
                rating=_rating(p),
                status=_status(p),
                map=_maps_link(p),
            )
        )
    return "\n".join(lines)


def _neighborhoods(hoods: List[Dict[str, Any]]) -> str:
    if not hoods:
        return "_No neighborhoods assessed._"

    scored = []
    for hood in hoods:
        fit = scoring.neighborhood_fit(hood.get("ratings") or {})
        scored.append((fit, hood))
    scored.sort(key=lambda row: (VERDICT_ORDER.get(row[1].get("verdict", "maybe"), 9), -row[0]))

    table = [
        "| Neighborhood | Verdict | Fit | Rent (furnished 1BR) | vs. Hai Chau |",
        "|---|---|---|---|---|",
    ]
    for fit, hood in scored:
        table.append(
            "| **{name}** | {verdict} | {fit}/100 | {rent} | {scale} |".format(
                name=_cell(hood.get("name")),
                verdict=VERDICT_BADGE.get(hood.get("verdict", ""), "—"),
                fit=_num(fit),
                rent=_cell(hood.get("rent_band_usd")),
                scale=_cell(hood.get("hai_chau_comparison")),
            )
        )
    lines = ["\n".join(table)]

    for fit, hood in scored:
        ratings = hood.get("ratings") or {}
        detail = ["### {name} — {verdict} · {fit}/100".format(
            name=hood.get("name", "?"),
            verdict=VERDICT_BADGE.get(hood.get("verdict", ""), "—"),
            fit=_num(fit),
        )]
        detail.append("")
        detail.append("**Why it works.** {why}".format(why=hood.get("why", "")))
        detail.append("")
        detail.append("**Downsides.** {down}".format(down=hood.get("downsides") or "none noted"))
        detail.append("")
        detail.append("**Best for.** {best}".format(best=hood.get("best_for") or "—"))
        detail.append("")
        detail.append("| " + " | ".join(
            criteria.SCORECARD_LABELS[scoring.RATING_TO_CRITERION[k]].split(" (")[0]
            for k in scoring.RATING_TO_CRITERION
        ) + " |")
        detail.append("|" + "---|" * len(scoring.RATING_TO_CRITERION))
        detail.append("| " + " | ".join(
            "{v}/10".format(v=int(scoring.clamp(float(ratings.get(k, 0)))))
            for k in scoring.RATING_TO_CRITERION
        ) + " |")
        lines.append("\n".join(detail))

    return "\n\n".join(lines)


def _housing(housing: Dict[str, Any]) -> str:
    if not housing:
        return "_No housing intel gathered._"
    parts = ["**What the budget actually buys.** {bands}".format(bands=housing.get("price_bands", ""))]

    sources = housing.get("where_to_look") or []
    if sources:
        rows = ["### Where to look", "", "| Channel | Kind | How to use it |", "|---|---|---|"]
        for source in sources:
            name = _cell(source.get("name"))
            if source.get("url"):
                name = "[{name}]({url})".format(name=name, url=source["url"])
            rows.append(
                "| {name} | {kind} | {notes} |".format(
                    name=name,
                    kind=_cell((source.get("kind") or "").replace("_", " ")),
                    notes=_cell(source.get("notes")),
                )
            )
        parts.append("\n".join(rows))

    if housing.get("lease_norms"):
        parts.append("### Lease norms\n\n{norms}".format(norms=housing["lease_norms"]))
    if housing.get("negotiation_notes"):
        parts.append("### Negotiating\n\n{notes}".format(notes=housing["negotiation_notes"]))
    flags = housing.get("red_flags") or []
    if flags:
        parts.append("### Red flags\n\n" + "\n".join("- " + flag for flag in flags))
    return "\n\n".join(parts)


def checklist_markdown(items: List[Dict[str, Any]]) -> str:
    by_phase: Dict[str, List[Dict[str, Any]]] = {phase: [] for phase in criteria.PHASE_ORDER}
    for item in items or []:
        by_phase.setdefault(item.get("phase", "research"), []).append(item)

    blocks = []
    for phase in criteria.PHASE_ORDER:
        title, generic = criteria.SOP_PHASES[phase]
        lines = ["### {title}".format(title=title), ""]
        for step in generic:
            lines.append("- [ ] {step}".format(step=step))
        specific = by_phase.get(phase) or []
        if specific:
            lines.append("")
            lines.append("_For this city:_")
            for item in specific:
                lines.append("- [ ] **{task}** — {why}".format(task=item.get("task", ""), why=item.get("why", "")))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render(findings: Dict[str, Any], budget: int = criteria.BUDGET_USD, generated: Optional[str] = None) -> str:
    generated = generated or datetime.datetime.now().strftime("%Y-%m-%d")
    city = findings.get("city", "Unknown")
    country = findings.get("country", "")
    heading = "# City Scout Report — {city}{country}".format(
        city=city, country=", {c}".format(c=country) if country else ""
    )

    out = [
        heading,
        "_Scouted {date} · budget ${budget}/mo furnished · generated by nomad-scout_".format(
            date=generated, budget=budget
        ),
        "",
        "## Bottom line",
        "",
        findings.get("bottom_line", "").strip(),
    ]

    if findings.get("best_neighborhood"):
        out.append("")
        out.append("**Target first: {hood}**".format(hood=findings["best_neighborhood"]))

    out.append("")
    out.append(_section("Neighborhoods", _neighborhoods(findings.get("neighborhoods") or [])))
    out.append(_section("Outdoor fitness", _fitness_table(findings.get("fitness") or [])))
    out.append(_section("Working cafes", _cafe_table(findings.get("cafes") or [])))
    out.append(_section("Food & groceries", _food_table(findings.get("food") or [])))
    out.append(_section("Housing", _housing(findings.get("housing") or {})))

    logistics = []
    for label, key in [
        ("Transit", "transit"),
        ("Internet", "connectivity"),
        ("Cost of living", "cost_of_living"),
        ("Visa", "visa_notes"),
    ]:
        if findings.get(key):
            logistics.append("**{label}.** {value}".format(label=label, value=findings[key]))
    if logistics:
        out.append(_section("Logistics", "\n\n".join(logistics)))

    watch_outs = findings.get("watch_outs") or []
    if watch_outs:
        out.append(_section("Watch-outs", "\n".join("- " + item for item in watch_outs)))

    out.append(_section("Pre-arrival checklist", checklist_markdown(findings.get("pre_arrival_checklist") or [])))

    sources = findings.get("sources") or []
    if sources:
        out.append(_section("Sources", "\n".join("- " + source for source in sources)))

    out.append(
        "---\n\n_Walk times without a Google Places lookup are estimates. Verify WiFi on "
        "Fast.com and noise at 8pm on a weekday before signing anything._\n"
    )
    return "\n".join(out)


def render_scorecard(name: str, scores: Dict[str, float], notes: str = "") -> str:
    total = scoring.weighted_score(scores)
    lines = [
        "# Apartment scorecard — {name}".format(name=name),
        "",
        "**{total}/100 — {verdict}**".format(total=_num(total), verdict=scoring.verdict(total)),
        "",
        "| Criterion | Score | Weight | Points |",
        "|---|---|---|---|",
    ]
    for _key, label, raw, weight, points in scoring.breakdown(scores):
        lines.append(
            "| {label} | {raw:.0f}/10 | {weight}% | {points} |".format(
                label=label, raw=raw, weight=weight, points=_num(points)
            )
        )
    lines.append("| **Total** | | **100%** | **{total}** |".format(total=_num(total)))

    losses = scoring.weakest(scores)
    if losses:
        lines.append("")
        lines.append("**Where it loses the most:**")
        for label, lost, weight in losses:
            lines.append("- {label} — costing {lost} of {weight} points".format(
                label=label, lost=_num(lost), weight=weight))

    lines.append("")
    lines.append("_80+ book it · 65-79 good · 50-64 maybe · below 50 pass._")
    if notes:
        lines.append("")
        lines.append("**Notes.** {notes}".format(notes=notes))
    return "\n".join(lines)

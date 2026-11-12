"""Orchestration: research pass -> structured extraction -> optional enrichment."""

import sys
from typing import Any, Dict, List, Optional

from . import client as api
from . import criteria, database, maps, prompts, report, schema


def _log(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def scout_city(
    city: str,
    neighborhoods: Optional[List[str]] = None,
    budget: int = criteria.BUDGET_USD,
    effort: str = "high",
    notes: Optional[str] = None,
    use_maps: bool = True,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Research a city end to end and return the saved database record."""
    anthropic_client = api.build_client()

    if not quiet:
        _log("Researching {city} (this takes a few minutes; each dot is a web search)".format(city=city))
    report_text = api.research(
        anthropic_client,
        system=prompts.system_prompt(),
        prompt=prompts.research_prompt(city, neighborhoods, budget, notes),
        effort=effort,
        progress=not quiet,
    )

    if not quiet:
        _log("Structuring findings")
    findings = api.extract(
        anthropic_client,
        prompt=prompts.extraction_prompt(report_text, city),
        schema=schema.FINDINGS_SCHEMA,
    )
    findings.setdefault("city", city)

    matched = 0
    if use_maps and maps.available():
        anchor = findings.get("best_neighborhood") or (neighborhoods[0] if neighborhoods else None)
        anchor_query = "{anchor}, {city}".format(anchor=anchor, city=city) if anchor else city
        if not quiet:
            _log("Verifying places on Google Maps (anchor: {anchor})".format(anchor=anchor_query))
        matched = maps.enrich(findings, anchor_query=anchor_query, progress=not quiet)
    elif use_maps and not quiet:
        _log("No GOOGLE_MAPS_API_KEY set — walk times and ratings are the model's estimates.")

    markdown = report.render(findings, budget=budget)
    path = database.write_report(city, markdown)

    record = database.upsert(
        city,
        {
            "city": findings.get("city", city),
            "country": findings.get("country", ""),
            "budget_usd": budget,
            "best_neighborhood": findings.get("best_neighborhood", ""),
            "bottom_line": findings.get("bottom_line", ""),
            "findings": findings,
            "raw_report": report_text,
            "report_path": path,
            "maps_verified": matched,
            "apartments": (database.get(city) or {}).get("apartments", []),
        },
    )
    return record

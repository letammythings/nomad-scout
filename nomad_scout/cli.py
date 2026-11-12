"""nomad-scout command line interface."""

import argparse
import datetime
import os
import sys
from typing import Any, Dict, List, Optional

from . import client as api
from . import criteria, database, maps, report, research, scoring

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- commands ---------------------------------------------------------------


def cmd_scout(args: argparse.Namespace) -> int:
    existing = database.get(args.city)
    if existing and not args.refresh:
        print(
            "{city} was already scouted on {date}.\n"
            "  See it:      nomad-scout show \"{city}\"\n"
            "  Re-research: nomad-scout scout \"{city}\" --refresh".format(
                city=existing.get("city", args.city), date=existing.get("updated_at", "?")
            )
        )
        return 0

    record = research.scout_city(
        city=args.city,
        neighborhoods=args.neighborhood,
        budget=args.budget,
        effort=args.effort,
        notes=args.notes,
        use_maps=not args.no_maps,
        quiet=args.quiet,
    )

    findings = record.get("findings", {})
    missing = maps.unverified(findings)

    print(report.render(findings, budget=args.budget))
    print()
    print("Saved to {path}".format(path=os.path.relpath(record["report_path"], PROJECT_ROOT)))
    if missing:
        print("Google Maps could not confirm: " + "; ".join(missing))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    record = database.get(args.city)
    if not record:
        print("No record for '{city}'. Run: nomad-scout scout \"{city}\"".format(city=args.city), file=sys.stderr)
        return 1
    if args.raw and record.get("raw_report"):
        print(record["raw_report"])
        return 0
    findings = record.get("findings")
    if findings:
        print(report.render(findings, budget=record.get("budget_usd", criteria.BUDGET_USD),
                            generated=record.get("updated_at")))
    else:
        print(_render_notes(record))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    cities = database.all_cities()
    if not cities:
        print("No cities scouted yet. Try: nomad-scout scout \"Chiang Mai\"")
        return 0
    width = max(len(c.get("city", "")) for c in cities)
    print("{n} cities in the database\n".format(n=len(cities)))
    for record in cities:
        best = record.get("best_neighborhood") or "—"
        print(
            "  {city:<{w}}  {date}  target: {best}".format(
                city=record.get("city", "?"), w=width, date=record.get("updated_at", "?"), best=best
            )
        )
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    cities = database.all_cities()
    if args.city:
        wanted = {database.slugify(c) for c in args.city}
        cities = [c for c in cities if c.get("slug") in wanted]
    rows = []
    for record in cities:
        findings = record.get("findings") or {}
        best_fit, best_name = 0.0, record.get("best_neighborhood") or "—"
        for hood in findings.get("neighborhoods") or []:
            fit = scoring.neighborhood_fit(hood.get("ratings") or {})
            if fit > best_fit:
                best_fit, best_name = fit, hood.get("name", best_name)
        rows.append((best_fit, record.get("city", "?"), best_name, record.get("updated_at", "?")))
    if not rows:
        print("Nothing to compare yet.")
        return 0
    rows.sort(key=lambda row: (-row[0], row[1]))
    print("{:<24} {:<8} {:<26} {}".format("City", "Fit", "Best neighborhood", "Scouted"))
    print("-" * 74)
    for fit, city, hood, date in rows:
        print("{:<24} {:<8} {:<26} {}".format(city, "{:.0f}".format(fit) if fit else "—", hood, date))
    return 0


def cmd_checklist(args: argparse.Namespace) -> int:
    record = database.get(args.city)
    findings = (record or {}).get("findings") or {}
    city_name = (record or {}).get("city", args.city)
    print("# Pre-arrival checklist — {city}\n".format(city=city_name))
    if not record:
        print("_No research on file yet — this is the generic SOP. "
              "Run `nomad-scout scout \"{city}\"` for the city-specific version._\n".format(city=args.city))
    print(report.checklist_markdown(findings.get("pre_arrival_checklist") or []))
    return 0


def _ask_score(label: str) -> float:
    while True:
        raw = input("  {label}: ".format(label=label)).strip()
        try:
            value = float(raw)
        except ValueError:
            print("    Enter a number 0-10.")
            continue
        if 0 <= value <= 10:
            return value
        print("    Must be between 0 and 10.")


def cmd_score(args: argparse.Namespace) -> int:
    name = args.name or input("Apartment name or address: ").strip() or "Unnamed apartment"
    print("\nScore each criterion 0-10. 10 fully meets it, 5 is mediocre, 0 fails.\n")
    scores: Dict[str, float] = {}
    for key, label in criteria.SCORECARD_LABELS.items():
        scores[key] = _ask_score("{label} ({w}%)".format(label=label, w=criteria.SCORECARD_WEIGHTS[key]))
    notes = input("\nNotes (optional): ").strip()

    card = report.render_scorecard(name, scores, notes)
    print()
    print(card)

    if args.city:
        record = database.get(args.city)
        if record is None:
            print("\n(Not saved — no database record for '{city}'.)".format(city=args.city), file=sys.stderr)
            return 0
        record.setdefault("apartments", []).append(
            {
                "name": name,
                "scores": scores,
                "total": scoring.weighted_score(scores),
                "verdict": scoring.verdict(scoring.weighted_score(scores)),
                "notes": notes,
                "scored_at": datetime.datetime.now().strftime("%Y-%m-%d"),
            }
        )
        database.upsert(record.get("city", args.city), record)
        print("\nSaved to the {city} record.".format(city=record.get("city", args.city)))
    return 0


def cmd_criteria(_args: argparse.Namespace) -> int:
    print("# The criteria\n")
    for section, items in criteria.NON_NEGOTIABLES.items():
        print("## {section}".format(section=section.title()))
        for item in items:
            print("- " + item)
        print()
    print("## Reference scale")
    for key, value in criteria.REFERENCE_SCALE.items():
        print("- {key}: {value}".format(key=key.replace("_", " "), value=value))
    print()
    print("## Apartment scorecard weights")
    for key, weight in criteria.SCORECARD_WEIGHTS.items():
        print("- {label}: {weight}%".format(label=criteria.SCORECARD_LABELS[key], weight=weight))
    print("\n80+ book it · 65-79 good · 50-64 maybe · below 50 pass")
    print("\nEdit nomad_scout/criteria.py to change any of this.")
    return 0


def _render_notes(record: Dict[str, Any]) -> str:
    """Render a seeded record that has prior notes but no full findings object."""
    lines = ["# {city}".format(city=record.get("city", "?"))]
    if record.get("source"):
        lines.append("_{source} · {date}_".format(source=record["source"], date=record.get("updated_at", "")))
    lines.append("")
    if record.get("bottom_line"):
        lines.append(record["bottom_line"])
        lines.append("")
    for heading, key in [
        ("Sweet spot", "sweet_spot"),
        ("Also good", "also_good"),
        ("Avoid", "avoid"),
        ("Outdoor fitness", "fitness"),
        ("Work cafes", "cafes"),
        ("Gyms", "gyms"),
        ("Transit", "transit"),
        ("Find apartments", "find_apartments"),
        ("Notes", "notes"),
    ]:
        value = record.get(key)
        if not value:
            continue
        lines.append("## {heading}".format(heading=heading))
        if isinstance(value, list):
            lines.extend("- " + str(item) for item in value)
        else:
            lines.append(str(value))
        lines.append("")
    lines.append("_Prior research carried over from the project brief. "
                 "Run `nomad-scout scout \"{city}\" --refresh` for a full report._".format(
                     city=record.get("city", "")))
    return "\n".join(lines)


# --- entry point ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nomad-scout",
        description="Scout a city for a nomad couple: neighborhood, pull-up bars, work cafes, food, and a place to live under $800.",
    )
    sub = parser.add_subparsers(dest="command")

    scout = sub.add_parser("scout", help="Research a city and write a City Scout Report")
    scout.add_argument("city")
    scout.add_argument("-n", "--neighborhood", action="append", help="Neighborhood to assess (repeatable)")
    scout.add_argument("-b", "--budget", type=int, default=criteria.BUDGET_USD, help="Monthly USD budget")
    scout.add_argument("--notes", help="Extra context to hand the researcher")
    scout.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    scout.add_argument("--refresh", action="store_true", help="Re-research a city already in the database")
    scout.add_argument("--no-maps", action="store_true", help="Skip Google Places verification")
    scout.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")
    scout.set_defaults(func=cmd_scout)

    show = sub.add_parser("show", help="Print a saved report")
    show.add_argument("city")
    show.add_argument("--raw", action="store_true", help="Print the original research prose instead")
    show.set_defaults(func=cmd_show)

    listing = sub.add_parser("list", help="List every city in the database")
    listing.set_defaults(func=cmd_list)

    compare = sub.add_parser("compare", help="Rank scouted cities by best-neighborhood fit")
    compare.add_argument("city", nargs="*", help="Limit to these cities")
    compare.set_defaults(func=cmd_compare)

    checklist = sub.add_parser("checklist", help="Print the pre-arrival checklist for a city")
    checklist.add_argument("city")
    checklist.set_defaults(func=cmd_checklist)

    score = sub.add_parser("score", help="Score an apartment you viewed against the scorecard")
    score.add_argument("--name", help="Apartment name or address")
    score.add_argument("--city", help="Save the result under this city's record")
    score.set_defaults(func=cmd_score)

    crit = sub.add_parser("criteria", help="Print the criteria and scorecard weights")
    crit.set_defaults(func=cmd_criteria)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    api.load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except api.ScoutError as err:
        print("\n{err}".format(err=err), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

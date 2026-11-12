"""The city database — one JSON file, so research is never repeated."""

import json
import os
import re
import datetime
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "cities.json")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "city"


def _empty_db() -> Dict[str, Any]:
    return {"version": 1, "cities": {}}


def load() -> Dict[str, Any]:
    if not os.path.exists(DB_PATH):
        return _empty_db()
    try:
        with open(DB_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return _empty_db()
    if not isinstance(data, dict) or "cities" not in data:
        return _empty_db()
    return data


def save(db: Dict[str, Any]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(db, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp, DB_PATH)


def get(city: str) -> Optional[Dict[str, Any]]:
    return load()["cities"].get(slugify(city))


def upsert(city: str, record: Dict[str, Any]) -> Dict[str, Any]:
    db = load()
    slug = slugify(city)
    existing = db["cities"].get(slug, {})
    record = dict(record)
    record.setdefault("city", city)
    record["slug"] = slug
    record["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d")
    record.setdefault("first_scouted", existing.get("first_scouted", record["updated_at"]))
    db["cities"][slug] = record
    save(db)
    return record


def remove(city: str) -> bool:
    db = load()
    if slugify(city) not in db["cities"]:
        return False
    del db["cities"][slugify(city)]
    save(db)
    return True


def all_cities() -> List[Dict[str, Any]]:
    cities = list(load()["cities"].values())
    cities.sort(key=lambda record: record.get("city", ""))
    return cities


def report_path(city: str) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    return os.path.join(REPORTS_DIR, "{slug}.md".format(slug=slugify(city)))


def write_report(city: str, markdown: str) -> str:
    path = report_path(city)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(markdown)
    return path

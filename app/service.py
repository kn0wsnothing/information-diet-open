import json
from datetime import datetime

from .catalog import validate_catalog
from .store import Store
from .time import HKT, hkt_date


def load_catalog(path: str) -> dict:
    """Load a user-provided local catalog; this operation never makes network requests."""
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    validate_catalog(payload)
    if "book" not in payload:
        raise ValueError("seed requires book")
    return payload


def prepare(db_path: str, catalog_path: str, day: str | None = None, now: str | None = None) -> str:
    current_day, timestamp = day or hkt_date(), now or datetime.now(HKT).isoformat()
    store = Store(db_path)
    store.setup()
    try:
        seed = load_catalog(catalog_path)
        store.seed_books(seed["book"])
        return "created" if store.generate(current_day, seed, timestamp) else "already-prepared"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        store.record_source_failure(current_day, timestamp, f"source load failed: {error}")
        return "failure"

"""Local setup and operation commands for Information Diet."""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from .config import catalog_path, data_dir, database_path
from .service import load_catalog
from .store import Store
from .time import HKT, hkt_date


def require_daily_slots(catalog: dict) -> None:
    """Reject incomplete input before creating a database or daily list."""
    kinds = {candidate["kind"] for candidate in catalog["candidates"]}
    missing = {"video", "podcast"} - kinds
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(
            "catalog needs at least one video and podcast before preparing a daily list; "
            f"add entries for: {names}"
        )


def init() -> int:
    destination = catalog_path()
    if destination.exists():
        raise ValueError(f"catalog already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    template = files("app").joinpath("examples/catalog.template.json")
    with template.open("rb") as source, destination.open("wb") as target:
        shutil.copyfileobj(source, target)
    print(f"Created {destination}. Edit it with your own book and saved links, then run information-diet validate.")
    return 0


def validate() -> int:
    catalog = load_catalog(str(catalog_path()))
    require_daily_slots(catalog)
    print(f"Catalog valid: {len(catalog['candidates'])} candidate(s).")
    return 0


def prepare(refresh: bool) -> int:
    catalog = load_catalog(str(catalog_path()))
    require_daily_slots(catalog)
    target = Store(database_path())
    target.setup()
    target.seed_books(catalog["book"])
    created = target.generate(hkt_date(), catalog, datetime.now(HKT).isoformat(), refresh=refresh)
    print("Prepared today’s list." if created else "Today’s list already exists.")
    return 0


def serve(host: str, port: int) -> int:
    import uvicorn

    print(f"Serving local data from {data_dir()} at http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="information-diet")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="write a catalog template to the local data directory")
    commands.add_parser("validate", help="validate the local catalog")
    prepare_parser = commands.add_parser("prepare", help="prepare today’s list from the local catalog")
    prepare_parser.add_argument("--refresh", action="store_true", help="reconsider deferred recommendations today")
    serve_parser = commands.add_parser("serve", help="serve the local page on loopback")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8422, type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "init": return init()
        if args.command == "validate": return validate()
        if args.command == "prepare": return prepare(args.refresh)
        return serve(args.host, args.port)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

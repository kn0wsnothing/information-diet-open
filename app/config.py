"""Paths for a local Information Diet installation."""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    configured = os.environ.get("INFORMATION_DIET_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    base = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser()
    return base / "information-diet"


def database_path() -> Path:
    return Path(os.environ.get("INFORMATION_DIET_DB", data_dir() / "information-diet.sqlite3")).expanduser()


def catalog_path() -> Path:
    return Path(os.environ.get("INFORMATION_DIET_CATALOG", data_dir() / "catalog.json")).expanduser()

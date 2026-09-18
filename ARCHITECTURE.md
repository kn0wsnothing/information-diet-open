# Architecture

Information Diet is a local FastAPI application backed by SQLite. `app/main.py` contains the web routes, `app/store.py` owns the selection and persistence rules, and `app/catalog.py` validates the user-maintained catalog.

The catalog is a local JSON file. `information-diet init` creates an empty template, `validate` checks it, and `prepare` writes a dated list into SQLite. No command fetches URLs or contacts a third-party service. This keeps the first installation useful for a person with a small set of saved links and avoids coupling daily use to an account, API, or importer.

`app/config.py` resolves the data directory and supports explicit environment overrides for the catalog and database. The server binds to loopback by default because this local application has no authentication. SQLite state remains after the process restarts.

Every feedback form carries the selected candidate identifier. The store compares that identifier inside its transaction, which prevents a stale browser submission from changing a recommendation that an explicit refresh already replaced. The same state layer persists media notes, listening progress, saved episodes, and book pages.

The repository does not include hosted accounts, automatic source ingestion, backups, or remote connectors. Those are separate operational choices, not hidden behavior in the local application.

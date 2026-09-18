# Architecture

The candidate is a FastAPI application backed by SQLite. `app/store.py` contains the daily selection and feedback logic. `app/main.py` presents that logic through a small HTML interface.

SQLite is intentional here: the page has one local user and needs durable state across reloads, not concurrent multi-user coordination. State mutations use short transactions. The database path is explicit through `SHOWCASE_DB`; when omitted it remains inside the candidate directory.

The application stores candidate identifiers with feedback. This prevents a late browser submission from applying to a replacement recommendation. The selection logic also separates `completed`, `continue`, `not_started`, and `not_interesting`, because these states have different consequences for the next list.

The bundled `examples/catalog.json` is synthetic. The public entrypoint reads only that file and a candidate-local SQLite path. It has no refresh adapters, services, source manifests, environment configuration for live state, or network calls.

The private system remains authoritative. This export demonstrates its application behavior and is not an export of a personal catalog, history, notes, or operational setup. It is intentionally a local demo: it does not provide authentication, backups, source ingestion, or production service management.

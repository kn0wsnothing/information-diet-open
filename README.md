# Information Diet showcase

A local, synthetic demonstration of a small daily page for reading, watching, and listening choices. It uses the production selection and SQLite state logic, with a candidate-local database and bundled sample catalog. See the [architecture notes](ARCHITECTURE.md), [MIT License](LICENSE), and [contribution policy](CONTRIBUTING.md).

The page deliberately makes a small set of decisions: it preserves one prepared list per day, carries unfinished items forward without creating a backlog, keeps listening separate from reading and watching, and records feedback against the specific candidate a person saw. A saved book target stays fixed for that day. These choices make progress visible without turning a missed item into debt.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
SHOWCASE_DB="$PWD/var/demo.sqlite3" .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8422
```

Open `http://127.0.0.1:8422`. The page prepares a synthetic list on first load. The SQLite file is local to the candidate and can be removed to reset the demo.

## Test

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Privacy and review limits

The bundled catalog is fictional. This candidate contains no personal catalog, reading history, notes, credentials, service files, refresh integrations, or private configuration. Its source package uses an allowlist and an exact Git revision during private review.

Automated checks can detect only a bounded set of privacy problems. A human must inspect the exact candidate and its diff before any release decision.

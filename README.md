# Information Diet

Information Diet is a small personal workspace for deciding what to read, watch, and listen to today. It turns a saved-media backlog into a short plan for the day: one video, one optional read, and one podcast.

![Daily page with fictional video, reading, and listening examples](assets/information-diet.png)

The full system prepares a short daily list with one video, one optional short read, and one podcast. It keeps that list stable through the day. You record what happened rather than pretend every recommendation was finished: completed, continue, did not start, or not interesting. That feedback affects later choices. An unfinished video or read can carry forward; a completed item does not return. A “did not start” item remains available until an explicit refresh chooses a replacement. The system therefore distinguishes “not today” from “never.”

Imagine opening the page at lunch. It might show a 24-minute video with a useful stopping point, a short article for a gap between meetings, and one long podcast for later. After ten minutes of the video, you can save its timestamp and a note. If you save the podcast, it moves to a separate listening list where you can record position and notes. The book section keeps a reported page number and a fixed target for the day, without creating catch-up debt.

## What you can inspect here

This repository is a local, runnable version of that workflow. It uses FastAPI for the page and SQLite for durable local state. The included catalog is fictional, but the daily selection, feedback, progress, saved-episode, and book-target logic are real application code.

SQLite suits the design because one local user needs state that survives a restart, rather than a multi-user service. Each change uses a short database transaction. Feedback carries the identifier of the recommendation the page displayed, so a late form submission cannot update a replacement item. A form token from the displayed page rejects submissions that did not come from that page.

The full system has a personal, inspected catalog and operating setup that are not included here. This demo has no account system, source ingestion, remote calls, backups, or service management. Its sample catalog exists only to make the behavior safe to run and inspect.

## Run it

Use Python 3.11 or later.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
SHOWCASE_DB="$PWD/var/demo.sqlite3" .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8422
```

Open `http://127.0.0.1:8422`. The first page load creates a synthetic daily list. Mark the video as “Started / keep this,” add a timestamp, or save the podcast and its listening position. The SQLite file at `var/demo.sqlite3` preserves those changes; delete it when you want a fresh demo.

The **Update recommendations** button is deliberate: it is the one action that can reconsider a deferred item. Reloading the page does not reshuffle the day’s list.

## Test

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The tests create temporary SQLite databases. They cover initial selection, feedback validation, rendered page content, and the difference between a reload and an explicit refresh.

## License and maintenance

Copyright (c) 2026 John. Released under the [MIT License](LICENSE). This project has one maintainer and does not accept external contributions; forks and reuse are welcome under the license. See [CONTRIBUTING.md](CONTRIBUTING.md).

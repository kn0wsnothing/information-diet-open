# Information Diet

Information Diet is a local application for choosing what to read, watch, and listen to today from your own saved-media backlog. It replaces an unbounded queue with a short daily list: one video, one optional read, and one podcast.

![Example daily page using fictional video, reading, and listening entries](assets/information-diet.png)

You supply the catalog. The app stores the choices and progress on your computer. A day’s list stays stable through reloads and restarts. Record whether you completed an item, want to continue it, did not start it, or are not interested. An unfinished item can carry forward; a completed item does not return. “Did not start” is distinct from rejection and is reconsidered only when you explicitly refresh the day.

The page also has a separate saved-episodes list for podcasts. You can save a suggested episode or add one manually, then keep its listening status, position, and notes. Video notes and timestamps stay with the selected item. A nonfiction book has a reported page number and a fixed daily target, so missed pages do not become catch-up debt.

## Install and create your catalog

Use Python 3.11 or later. Installation creates a normal local Python package with an `information-diet` command.

```bash
git clone https://github.com/kn0wsnothing/information-diet-showcase.git information-diet
cd information-diet
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/information-diet init
```

`init` writes `catalog.json` to `~/.local/share/information-diet/` by default. Set `INFORMATION_DIET_DATA_DIR` before running it to use another directory. The template is deliberately empty: edit it with your own book and saved links before preparing a list.

Each candidate needs an `id`, `kind` (`video`, `read`, or `podcast`), title, summary, reason, direct URL, inspection method, inspection date, and provenance. “Inspection” simply records how you checked the item before adding it; “provenance” records where you saved or found it. Videos and podcasts also need a positive duration. A video’s `source_url` must be a native YouTube watch link; a podcast’s `url` must be an HTTPS episode link.

Copy [the complete catalog example](app/examples/catalog.example.json) when you want a starting shape. Replace every title, URL, summary, reason, and placeholder identifier with your own material. `book` accepts `nonfiction_title`, optional `author` and `total_pages`, `reported_page`, `daily_pace`, and optional `fiction_title`. The [catalog validation code](app/catalog.py) is the precise reference for optional podcast and video links.

This first version uses a manual JSON catalog by design. It works with links you have already chosen, requires no account or API key, and makes no network request while validating or preparing a list. Importers and source connectors are not included.

## Use it every day

```bash
.venv/bin/information-diet validate
.venv/bin/information-diet prepare
.venv/bin/information-diet serve
```

Open `http://127.0.0.1:8422`. The app is loopback-only by default because it has no user authentication. Do not expose it directly to a network.

`prepare` reads your catalog and creates today’s list. It does not create sample recommendations. Run it again tomorrow for a new list. Use `prepare --refresh` only when you want the app to reconsider today’s deferred recommendations.

The database defaults to `~/.local/share/information-diet/information-diet.sqlite3`. Set `INFORMATION_DIET_DB` or `INFORMATION_DIET_CATALOG` to use separate paths. Stop and start `serve` again to confirm that saved episodes, notes, feedback, and book progress remain.

## Engineering choices and limits

The application is FastAPI plus SQLite. SQLite fits one person’s durable local state without requiring a server database. Each mutation runs in a short transaction, and feedback includes the identifier of the recommendation shown in the form so a stale submission cannot update a replacement item. Forms use a per-process token to reject submissions that did not come from the displayed page.

The repository contains the real routing, selection, persistence, template, and catalog-validation code. It does not include accounts, a hosted deployment, automatic source ingestion, backups, or remote service integrations.

## Test

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests use temporary databases and catalogs. They cover catalog validation, selection and refresh behavior, stale feedback, saved episodes, notes, progress, and persistence.

## License and maintenance

Copyright (c) 2026 John. Released under the [MIT License](LICENSE). This project has one maintainer and does not accept external contributions; forks and reuse are welcome under the license. See [CONTRIBUTING.md](CONTRIBUTING.md).

# Information Diet agent guide

Use the installed `information-diet` command and the local browser page as the daily media tool. Do not edit the SQLite database directly. Do not browse, scrape, fetch URLs, or invent catalog facts. The application itself makes no network request while validating or preparing a list.

## Files, setup, and status

The default data directory is `~/.local/share/information-diet/`. It contains `catalog.json` and `information-diet.sqlite3`. `INFORMATION_DIET_DATA_DIR` changes both paths. `INFORMATION_DIET_CATALOG` and `INFORMATION_DIET_DB` can set each path separately.

Run these commands after the human has installed the package:

```sh
information-diet init
information-diet validate
information-diet prepare [--refresh]
information-diet serve [--host 127.0.0.1] [--port 8422]
```

`init` refuses to overwrite an existing catalog. `validate` and `prepare` fail with exit code `2` for missing or invalid data. A usable catalog needs at least one `video` and one `podcast`; `read` is optional. `prepare` prints either `Prepared today’s list.` or `Today’s list already exists.` `--refresh` only reconsideres deferred recommendations for today. `serve` runs the FastAPI page at the configured loopback address; do not expose it to a network because it has no authentication.

## Catalog contract

Start from [the shipped catalog example](app/examples/catalog.example.json), but replace every placeholder with human supplied material. The top level has `book` and `candidates`. Each candidate requires string `id`, `kind`, `title`, `summary`, `why`, `url`, `inspection_method`, `inspected_at`, and `provenance`.

`kind` is `video`, `read`, or `podcast`. `inspected_at` is ISO 8601. Videos and podcasts need a positive integer `duration_minutes`. A video must use the same native HTTPS YouTube watch URL for `url` and `source_url`. A podcast `url` must be a direct HTTPS episode link. `book` needs `nonfiction_title`, `reported_page`, and `daily_pace`; `author`, `total_pages`, and `fiction_title` are optional. Run `validate` after each catalog change.

When the human gives saved links and notes, you may draft a catalog from only that material. Explain missing required details instead of guessing. Show the proposed JSON before first write or a material catalog change. The user’s explicit request to write, validate, or prepare authorizes that bounded command. Ask when source, metadata, or the desired change is ambiguous.

## Daily workflow

Prepare the list, then tell the human to use the browser page for feedback and notes:

```sh
information-diet validate
information-diet prepare
information-diet serve
```

Expected result: the page at `http://127.0.0.1:8422` shows a video and podcast, plus a read when supplied. Browser submissions persist feedback, book pages, media notes, saved episodes, and listening position in SQLite. A stale form is rejected if a refresh replaced its recommendation.

## Useful prompts for the human

- “Read the Information Diet agent guide and inspect my local catalog. Tell me what is missing. Do not change anything.”
- “Turn these saved links and my notes into a proposed catalog. Do not browse or infer missing metadata. Show the JSON before writing it.”
- “I approve the proposed catalog. Write it, validate it, prepare today’s list, and tell me the local browser address.”
- “My list is prepared. Explain what `--refresh` would change, but do not run it until I ask.”
- “Help me add this episode to my catalog using only these details. If its direct URL or duration is missing, ask me for it.”

## Human approval boundary

An assistant may read local state and perform an explicitly requested catalog write, validation, preparation, or server start. It must not create media facts, fetch sources, expose the server, delete local data, or refresh a daily list without the user’s request. It must not claim an external integration or plugin exists.

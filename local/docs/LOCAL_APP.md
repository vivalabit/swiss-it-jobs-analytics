# Local Vacancy App

This document covers the local web application exposed by
`swiss_jobs.cli.local_search_web`. It focuses on the app UI, what each screen
does, and which actions read or write local data.

For the full command-line workflow, data model, installation steps, and public
statistics pipeline, see [TECHNICAL_USAGE.md](TECHNICAL_USAGE.md).

## 1. What the App Does

The local app runs a browser UI on top of repository-local SQLite databases. It
supports four practical tasks:

- browse and search vacancies already stored in local databases;
- start vacancy parser runs from the UI;
- start AI analysis runs from the UI;
- build public statistics snapshots from selected local databases.

The app binds to `127.0.0.1` by default. Vacancy browsing opens SQLite files in
read-only mode. Parser, AI analysis, and public stats actions start subprocesses
that can write to project output directories.

## 2. Start the App

Start the app from the repository root:

```bash
python3 -m swiss_jobs.cli.local_search_web --port 8765 --open
```

Without `--open`, open the page manually:

```text
http://127.0.0.1:8765
```

By default, the app loads existing databases from:

```text
runtime/*/main-config/*.sqlite
```

To load specific databases:

```bash
python3 -m swiss_jobs.cli.local_search_web \
  --database-path runtime/jobs_ch/main-config/jobs_ch.sqlite \
  --database-path runtime/jobup_ch/main-config/jobup_ch.sqlite \
  --port 8765 \
  --open
```

Available launch options:

- `--database-path`: SQLite file to load. Can be repeated.
- `--host`: bind host. Defaults to `127.0.0.1`.
- `--port`: bind port. Defaults to `8765`.
- `--open`: open the local page in the default browser.

## 3. App Screens

The main menu contains:

- `Vacancy Browser`: browse and search loaded local databases.
- `Vacancy Search`: start parser runs for selected providers.
- `AI Analyse`: start AI enrichment for selected providers.
- `Public Stats`: build aggregated public statistics snapshots.
- `Settings`: reserved settings area.

The log drawer shows generated commands, stdout/stderr lines, progress events,
and final process status.

## 4. Vacancy Browser

`Vacancy Browser` searches only the SQLite databases loaded when the app
started. It does not fetch remote job boards and does not modify database rows.

Available filters:

- `Job title, keywords, or company`: searches title, company, location,
  description, and salary text.
- `Keywords`: searches extracted terms and stored analytics JSON.
- `Source`: filters by source value.
- `Location`: filters by normalized location terms.
- `Company`: filters by company name.
- `Role`: filters by role family terms.
- `Seniority`: filters by inferred seniority.
- `Required skill`: filters by technical terms such as languages, frameworks,
  platforms, tools, databases, vendors, and methods.
- `Date field`: chooses `Last seen`, `First seen`, or `Published` for date
  filtering.
- `Date from` / `Date to`: accepts `dd.mm.yyyy`.
- `Salary Range (CHF)`: filters by normalized salary bounds.
- `Salary`: optionally returns only vacancies with salary data.

Each result card can show:

- source and backing database;
- title, company, location, URL, and publication date;
- salary, role, seniority, remote mode, and employment type when available;
- matched keywords and detected skills;
- description preview;
- raw details from `analytics_json`, `llm_analysis_json`, raw JSON, and job
  posting schema fields.

Use `Loaded local databases` in the left panel to see which files are connected.
Use the `i` menu in the toolbar for per-database counts.

## 5. Vacancy Search

`Vacancy Search` starts parser subprocesses for selected sources. The backend
runs one command per selected source:

```text
python -m swiss_jobs.cli.parse --source <source> ...
```

UI fields passed to the parser:

- selected sources;
- `Mode`: `search` or `new`;
- `Canton`;
- `Search term`;
- `Location`;
- `Max pages`;
- `Detail limit`.

`Preview Command` writes a command preview to the log drawer without running the
parser.

`Run Parser` starts the selected sources sequentially. Parsed vacancies are
written by the parser into each source's runtime database, typically:

```text
runtime/<source>/main-config/<source>.sqlite
```

After the run finishes, the app reloads facets and search results so new rows
can be inspected in `Vacancy Browser`.

## 6. AI Analyse

`AI Analyse` starts AI enrichment subprocesses for selected sources. The backend
runs one command per selected source:

```text
python -m swiss_jobs.cli.analyze_vacancies_llm --source <source> ...
```

UI fields currently passed to the backend:

- selected sources;
- `Vacancy scope`;
- `Model`;
- `Vacancy limit`.

The current backend does not use `First seen from`, `First seen to`,
`Batch size`, or `Analysis focus`.

Scope behavior:

- `new vacancies only`: uses the analyzer default scope; if a limit is set, it
  adds `--limit`.
- `missing AI analysis`: currently behaves the same as `new vacancies only`.
- `all selected vacancies`: adds `--include-analyzed`; if no limit is set, it
  adds `--all`.

AI results are saved back into the source SQLite database, including:

```text
llm_analysis_json
llm_model
llm_analyzed_at
```

After completion, the app reloads facets and search results. Result cards can
then expose the model, analysis timestamp, and analysis JSON.

## 7. Public Stats

`Public Stats` builds aggregated public statistics from selected runtime
databases. This is a write action.

The backend runs these stages:

1. `analytics`: calls `scripts/export_analytics.py` and writes CSV files to
   `analytics_output`.
2. `snapshot`: calls `scripts/build_public_stats.py` and writes JSON/CSV files
   under the selected output directory, defaulting to `public_stats`.
3. `site-sync`: calls `node site/scripts/sync-public-data.mjs` to copy public
   stats into `site/public` and rebuild downloadable ZIP archives.

UI fields currently used by the backend:

- selected sources;
- `Output directory`;
- sync enabled by default.

`Site data directory` is shown in the UI, but the backend currently uses the
standard `site/scripts/sync-public-data.mjs` script. `Snapshot date` and
`Salary group minimum` are not currently passed to the backend.

Successful output can include:

```text
analytics_output/*.csv
public_stats/data/*.json
public_stats/csv/*.csv
site/public/data/*.json
site/public/csv/*.csv
site/public/downloads/*.zip
```

## 8. Local API

The app exposes local JSON endpoints used by the UI:

- `GET /health`
- `GET /api/facets`
- `GET /api/search`
- `POST /api/parser-runs`
- `GET /api/parser-runs?run_id=...&after=...`
- `POST /api/ai-analysis-runs`
- `GET /api/ai-analysis-runs?run_id=...&after=...`
- `POST /api/public-stats-runs`
- `GET /api/public-stats-runs?run_id=...&after=...`

These endpoints are intended for local use. Do not expose the app to a public
network without adding authentication and process-level safeguards.

## 9. Operational Notes

Parser, AI, and public stats runs are tracked in memory. If the local app
process exits, active run state and log history are lost.

The log drawer keeps only the latest in-memory run messages. Long runs may drop
older messages after the internal log cap is reached.

The browser view uses the database files loaded at app startup. If you create a
new database path outside those files, restart the app with the relevant
`--database-path`.

Public stats output can be empty if the selected data does not meet the public
analytics requirements described in [TECHNICAL_USAGE.md](TECHNICAL_USAGE.md),
especially the `publication_date >= 2026-01-01` coverage rule.

# Technical Usage: Search and AI Analysis

Short guide for local vacancy workflows: collecting data, searching stored SQLite databases, and running AI analysis.

## 1. Setup

Run commands from the repository root.

```bash
python3 -m pip install -e .
```

AI analysis requires an OpenAI API key. Export it in your shell or place it in `.env` in the repository root:

```bash
OPENAI_API_KEY=sk-...
```

Default local databases are stored under:

```text
runtime/<source>/main-config/<source>.sqlite
```

Supported `source` values:

```text
jobs_ch
jobscout24_ch
jobup_ch
linked_in
swissdevjobs_ch
```

## 2. Collect Vacancies

Collect vacancies from one source:

```bash
python3 -m swiss_jobs.cli.parse --source swissdevjobs_ch --mode search --term python --location zurich --max-pages 3
```

Collect vacancies from all sources using default configs:

```bash
python3 -m swiss_jobs.cli.parse --all-sources --mode search --term python --location zurich --max-pages 3
```

Useful options:

- `--source` - vacancy source to run.
- `--all-sources` - run all sources in parallel.
- `--mode new` - collect latest vacancies.
- `--mode search` - collect vacancies by term and location.
- `--term` / `--terms` - one or more search terms.
- `--location` / `--locations` - one or more locations.
- `--canton zh` - canton code for default location filtering.
- `--max-pages 3` - limit scanned pages.
- `--detail-limit 20` - limit detail-page enrichment.
- `--database-path path/to/file.sqlite` - write to a specific SQLite file.
- `--json` - print JSON output.

## 3. Search Stored Vacancies

CLI search uses already-created SQLite databases. If `--database-path` is omitted, existing databases from `runtime/*/main-config/*.sqlite` are used.

```bash
python3 -m swiss_jobs.cli.search_vacancies --term python --term django --limit 20
```

Search with salary filters:

```bash
python3 -m swiss_jobs.cli.search_vacancies --term data --has-salary --salary-min 120000 --salary-currency CHF --limit 10
```

JSON output for further processing:

```bash
python3 -m swiss_jobs.cli.search_vacancies --term devops --json --limit 50
```

Useful options:

- `--term` - text matched against title, company, location, description, and salary text. Can be repeated or comma-separated.
- `--source jobs.ch` - filter by the stored source value.
- `--salary-min` / `--salary-max` - salary range.
- `--salary-currency CHF` - salary currency.
- `--salary-unit YEAR` - salary period.
- `--has-salary` - return only vacancies with normalized salary data.
- `--limit 0` - return all matches.

## 4. Local Search Web UI

Start the read-only web UI:

```bash
python3 -m swiss_jobs.cli.local_search_web --port 8765 --open
```

Use specific databases:

```bash
python3 -m swiss_jobs.cli.local_search_web --database-path runtime/jobs_ch/main-config/jobs_ch.sqlite --database-path runtime/jobup_ch/main-config/jobup_ch.sqlite
```

The UI is available at:

```text
http://127.0.0.1:8765
```

## 5. AI Vacancy Analysis

AI analysis enriches stored vacancies with structured fields and saves results into `llm_analysis_json`, `llm_model`, and `llm_analyzed_at`.

Estimate cost before running analysis:

```bash
python3 -m swiss_jobs.cli.analyze_vacancies_llm --source swissdevjobs_ch --limit 100 --estimate-cost
```

Preview results without writing to the database:

```bash
python3 -m swiss_jobs.cli.analyze_vacancies_llm --source swissdevjobs_ch --limit 5 --dry-run
```

Run analysis and save results:

```bash
python3 -m swiss_jobs.cli.analyze_vacancies_llm --source swissdevjobs_ch --limit 100
```

Analyze all not-yet-analyzed vacancies for a source:

```bash
python3 -m swiss_jobs.cli.analyze_vacancies_llm --source swissdevjobs_ch --all
```

Useful options:

- `--source` - source key: `jobs_ch`, `jobscout24_ch`, `jobup_ch`, `linked_in`, `swissdevjobs_ch`.
- `--database-path` - use a specific SQLite database instead of the default source database.
- `--model gpt-5-nano` - OpenAI model.
- `--limit 100` - number of vacancies to process.
- `--offset 100` - skip the first N matching vacancies.
- `--all` - process all matching vacancies.
- `--include-analyzed` - include vacancies that already have AI analysis.
- `--dry-run` - do not write results to the database.
- `--estimate-cost` - estimate token usage and cost only.
- `--quiet` - disable progress logs.

## 6. Safe Run Order

Recommended workflow for a new source:

```bash
python3 -m swiss_jobs.cli.parse --source swissdevjobs_ch --mode search --term python --location zurich --max-pages 3
python3 -m swiss_jobs.cli.search_vacancies --term python --limit 10
python3 -m swiss_jobs.cli.analyze_vacancies_llm --source swissdevjobs_ch --limit 100 --estimate-cost
python3 -m swiss_jobs.cli.analyze_vacancies_llm --source swissdevjobs_ch --limit 5 --dry-run
python3 -m swiss_jobs.cli.analyze_vacancies_llm --source swissdevjobs_ch --limit 100
```

## 7. Common Errors

- `No default runtime SQLite databases found` - collect vacancies first or pass `--database-path`.
- `OPENAI_API_KEY is not set` - add the key to `.env` or export it as an environment variable.
- Empty search results - check `--term`, `--source`, salary filters, and whether `runtime` contains data.
- Slow collection - reduce `--max-pages`, `--detail-limit`, or `--detail-workers`.

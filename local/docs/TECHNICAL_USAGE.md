# Technical Documentation: Build Your Own Vacancy Statistics

This guide explains how to collect local vacancy data, enrich it with AI analysis,
and generate your own Swiss IT job market statistics from the repository.

The workflow has four stages:

1. Collect vacancies into local SQLite databases.
2. Optionally enrich vacancies with AI analysis.
3. Export aggregated analytics CSV files.
4. Build public JSON snapshots and preview them in the local site.

Run all commands from the repository root unless a section says otherwise.

## 1. Requirements

Install the project in editable mode:

```bash
python3 -m pip install -e .
```

AI analysis requires an OpenAI API key. Export it in your shell:

```bash
export OPENAI_API_KEY=sk-...
```

Or place it in a repository-local `.env` file:

```text
OPENAI_API_KEY=sk-...
```

The public site preview also requires Node.js dependencies:

```bash
cd site
npm ci
cd ..
```

## 2. Data Model

The statistics exporter accepts one or more datasets in these formats:

- `.csv`
- `.parquet`
- `.json`
- `.jsonl`
- `.sqlite`
- `.db`

SQLite files created by this project can be used directly. Default local
databases are stored under:

```text
runtime/<source>/main-config/<source>.sqlite
```

Supported source keys are:

```text
jobs_ch
jobscout24_ch
jobup_ch
linked_in
swissdevjobs_ch
```

For external CSV, JSON, JSONL, or Parquet files, the exporter expects at least
these normalized fields, or one of their supported aliases:

| Canonical field | Purpose |
| --- | --- |
| `company` | Employer name. |
| `role_category` | Main role family, for example `software_engineering`, `data_ai`, or `devops_platform`. |
| `city` | Vacancy city or locality. |
| `canton` | Swiss canton code or canton name. |
| `seniority` | Seniority label, for example `junior`, `mid`, or `senior`. |
| `work_mode` | Work mode, for example `onsite`, `hybrid`, or `remote`. |
| `skills` | Skill list. Lists can be JSON arrays, Python-style lists, comma-separated text, or `|`-separated text. |

Recommended fields:

| Field | Why it matters |
| --- | --- |
| `vacancy_id` | Enables deduplication across repeated imports. |
| `source` | Helps identify where each vacancy came from. |
| `title` | Improves deduplication and experience/seniority inference. |
| `description_text` | Used for education and experience requirement summaries. |
| `publication_date` | Required for non-empty public statistics and trend tables. Public analytics include vacancies published from `2026-01-01` onward. |
| `first_seen_at` / `last_seen_at` | Used for vacancy lifecycle and closed-vacancy trend metrics. |
| `programming_languages` | Creates programming language summaries. |
| `frameworks_libraries` | Creates framework and library summaries. |
| `salary_min` / `salary_max` | Creates salary summaries. |
| `salary_currency` | Use `CHF` for comparable Swiss salary statistics. |
| `salary_unit` | Use `YEAR` for annual salary statistics. |

Example minimal CSV:

```csv
vacancy_id,company,role_category,city,canton,seniority,work_mode,skills,programming_languages,frameworks_libraries,salary_min,salary_max,salary_currency,salary_unit,publication_date
sample-001,Alpine Data,data_ai,Zürich,ZH,senior,hybrid,"python|sql|airflow","python|sql","airflow|pandas",115000,140000,CHF,YEAR,2026-04-20T10:00:00+02:00
sample-002,Helvetic Cloud,devops_platform,Bern,BE,mid,remote,"aws|terraform|kubernetes","python|bash","terraform",105000,130000,CHF,YEAR,2026-04-21T10:00:00+02:00
```

## 3. Collect Vacancies

Collect vacancies from one source:

```bash
python3 -m swiss_jobs.cli.parse --source swissdevjobs_ch --mode search --term python --location zurich --max-pages 3
```

Collect vacancies from all configured sources:

```bash
python3 -m swiss_jobs.cli.parse --all-sources --mode search --term python --location zurich --max-pages 3
```

Useful collection options:

- `--source`: source key to run.
- `--all-sources`: run all sources in parallel.
- `--mode new`: collect latest vacancies.
- `--mode search`: collect vacancies by term and location.
- `--term` / `--terms`: one or more search terms.
- `--location` / `--locations`: one or more locations.
- `--canton zh`: canton code for default location filtering.
- `--max-pages 3`: limit scanned pages.
- `--detail-limit 20`: limit detail-page enrichment.
- `--database-path path/to/file.sqlite`: write to a specific SQLite file.
- `--json`: print JSON output.

After collection, confirm that data exists:

```bash
python3 -m swiss_jobs.cli.search_vacancies --term python --limit 10
```

Search across existing default databases:

```bash
python3 -m swiss_jobs.cli.search_vacancies --term python --term django --limit 20
```

Search with salary filters:

```bash
python3 -m swiss_jobs.cli.search_vacancies --term data --has-salary --salary-min 120000 --salary-currency CHF --limit 10
```

Print JSON for downstream checks:

```bash
python3 -m swiss_jobs.cli.search_vacancies --term devops --json --limit 50
```

## 4. Optional: Inspect Data in the Local Web UI

Start the read-only local search UI:

```bash
python3 -m swiss_jobs.cli.local_search_web --port 8765 --open
```

Use specific databases:

```bash
python3 -m swiss_jobs.cli.local_search_web --database-path runtime/jobs_ch/main-config/jobs_ch.sqlite --database-path runtime/jobup_ch/main-config/jobup_ch.sqlite
```

Open:

```text
http://127.0.0.1:8765
```

## 5. Optional: Run AI Vacancy Analysis

AI analysis enriches stored vacancies with structured fields such as role family,
seniority, work mode, technologies, and location details. Results are saved back
to the SQLite database in these columns:

- `llm_analysis_json`
- `llm_model`
- `llm_analyzed_at`

Estimate cost before writing anything:

```bash
python3 -m swiss_jobs.cli.analyze_vacancies_llm --source swissdevjobs_ch --limit 100 --estimate-cost
```

Preview output without saving:

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

Useful AI options:

- `--source`: source key.
- `--database-path`: use a specific SQLite database instead of the default source database.
- `--model gpt-5-nano`: OpenAI model.
- `--limit 100`: number of vacancies to process.
- `--offset 100`: skip the first matching vacancies.
- `--all`: process all matching vacancies.
- `--include-analyzed`: include vacancies that already have AI analysis.
- `--dry-run`: do not write results to the database.
- `--estimate-cost`: estimate token usage and cost only.
- `--quiet`: disable progress logs.

## 6. Export Analytics CSV Files

Use `scripts/export_analytics.py` to turn one or more datasets into aggregated
CSV statistics.

From project-created SQLite databases:

```bash
python3 scripts/export_analytics.py \
  runtime/jobs_ch/main-config/jobs_ch.sqlite \
  runtime/jobscout24_ch/main-config/jobscout24_ch.sqlite \
  runtime/jobup_ch/main-config/jobup_ch.sqlite \
  runtime/linked_in/main-config/linked_in.sqlite \
  runtime/swissdevjobs_ch/main-config/swissdevjobs_ch.sqlite \
  --output-dir analytics_output \
  --salary-group-minimum 10
```

From an external CSV snapshot:

```bash
python3 scripts/export_analytics.py data/private_snapshots/your_snapshot.csv --output-dir analytics_output
```

Control top-list sizes:

```bash
python3 scripts/export_analytics.py data/private_snapshots/your_snapshot.csv \
  --output-dir analytics_output \
  --top-skills 30 \
  --top-pairs 100 \
  --salary-group-minimum 10
```

The exporter writes CSV files such as:

- `analytics_output/overview_metrics.csv`
- `analytics_output/distribution_company.csv`
- `analytics_output/distribution_canton.csv`
- `analytics_output/top_skills_overall.csv`
- `analytics_output/top_skills_by_role_category.csv`
- `analytics_output/salary_summary.csv`
- `analytics_output/vacancy_trends_daily.csv`
- `analytics_output/city_map_details.csv`

During export, the project automatically:

- standardizes supported column aliases;
- normalizes city and canton values where possible;
- deduplicates vacancies across sources;
- excludes known staffing and recruitment agencies;
- filters public statistics to vacancies published from `2026-01-01` onward;
- calculates distributions, salary summaries, skill rankings, trend tables, and map data.

## 7. Optional: Export a Deduplication Report

Use this when you want to inspect which vacancies were treated as cross-source
duplicates:

```bash
python3 scripts/export_dedup_report.py \
  runtime/jobs_ch/main-config/jobs_ch.sqlite \
  runtime/jobup_ch/main-config/jobup_ch.sqlite \
  --output-path analytics_output/cross_source_dedup_report.csv
```

Include staffing agencies in the report:

```bash
python3 scripts/export_dedup_report.py data/private_snapshots/your_snapshot.csv \
  --include-staffing-agencies \
  --output-path analytics_output/cross_source_dedup_report.csv
```

## 8. Build Public JSON Snapshots

The frontend consumes compact JSON files, not the raw analytics CSV files. Build
those snapshots from `analytics_output`:

```bash
python3 scripts/build_public_stats.py \
  --csv-dir analytics_output \
  --output-dir public_stats/data \
  --copy-csv-dir public_stats/csv \
  --snapshot-date 2026-04-22
```

This writes:

- `public_stats/data/*.json`: compact frontend snapshots.
- `public_stats/csv/*.csv`: public-safe CSV exports.

These outputs can be committed as the current public statistics snapshot.
SQLite databases and raw vacancy descriptions should not be published unless you
explicitly intend to share them.

## 9. Preview the Statistics Site

Start the frontend:

```bash
cd site
npm run dev
```

The `predev` script copies `public_stats/data` and `public_stats/csv` into the
site public directory before Vite starts.

Open the URL printed by Vite, usually:

```text
http://localhost:5173
```

Build the static site:

```bash
cd site
npm run build
```

## 10. Recommended End-to-End Workflow

For a small first run:

```bash
python3 -m pip install -e .

python3 -m swiss_jobs.cli.parse \
  --source swissdevjobs_ch \
  --mode search \
  --term python \
  --location zurich \
  --max-pages 3

python3 -m swiss_jobs.cli.search_vacancies --term python --limit 10

python3 -m swiss_jobs.cli.analyze_vacancies_llm \
  --source swissdevjobs_ch \
  --limit 100 \
  --estimate-cost

python3 -m swiss_jobs.cli.analyze_vacancies_llm \
  --source swissdevjobs_ch \
  --limit 5 \
  --dry-run

python3 -m swiss_jobs.cli.analyze_vacancies_llm \
  --source swissdevjobs_ch \
  --limit 100

python3 scripts/export_analytics.py \
  runtime/swissdevjobs_ch/main-config/swissdevjobs_ch.sqlite \
  --output-dir analytics_output

python3 scripts/build_public_stats.py \
  --csv-dir analytics_output \
  --output-dir public_stats/data \
  --copy-csv-dir public_stats/csv

cd site
npm run dev
```

For a run across all sources:

```bash
python3 -m swiss_jobs.cli.parse \
  --all-sources \
  --mode search \
  --term python \
  --location zurich \
  --max-pages 3

python3 scripts/export_analytics.py \
  runtime/jobs_ch/main-config/jobs_ch.sqlite \
  runtime/jobscout24_ch/main-config/jobscout24_ch.sqlite \
  runtime/jobup_ch/main-config/jobup_ch.sqlite \
  runtime/linked_in/main-config/linked_in.sqlite \
  runtime/swissdevjobs_ch/main-config/swissdevjobs_ch.sqlite \
  --output-dir analytics_output

python3 scripts/build_public_stats.py \
  --csv-dir analytics_output \
  --output-dir public_stats/data \
  --copy-csv-dir public_stats/csv
```

## 11. GitHub Actions Workflow

The repository includes `.github/workflows/build_public_stats.yml`.

When triggered manually, it can rebuild public statistics from dataset paths
provided in the workflow input. If no paths are provided, it looks for snapshot
files under:

```text
data/private_snapshots/
```

Supported private snapshot formats are the same as the local exporter:

```text
.csv, .parquet, .json, .jsonl, .sqlite, .db
```

If committed public snapshots already exist and no private snapshot input is
provided, the workflow can build the site from the committed `public_stats`
files.

## 12. Troubleshooting

`No default runtime SQLite databases found`

Collect vacancies first, or pass one or more explicit `--database-path` values.

`OPENAI_API_KEY is not set`

Export the key in the shell or add it to `.env`.

Empty search results

Check the search terms, source filters, salary filters, and whether the
`runtime` directory contains data.

Analytics output has zero vacancies

Check that your dataset has `publication_date` values on or after `2026-01-01`.
Public analytics intentionally filter out older postings.

Missing columns error during export

Add the required fields listed in the data model section, or rename your input
columns to one of the supported aliases.

Slow collection

Reduce `--max-pages`, `--detail-limit`, or `--detail-workers`.

Frontend does not show new data

Run `python3 scripts/build_public_stats.py` first, then restart `npm run dev` in
the `site` directory so the `predev` sync step copies the latest snapshots.

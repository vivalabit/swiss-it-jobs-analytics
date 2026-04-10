# Swiss IT Job Market Analytics

Multi-source vacancy parsing and analytics for the Swiss IT job market.

## Suggested file tree

```text
.
├── runtime/
│   └── jobs_ch/
├── swiss_jobs/
│   ├── cli/
│   │   └── parse.py
│   ├── core/
│   │   ├── archive.py
│   │   ├── database.py
│   │   ├── filters.py
│   │   ├── formatter.py
│   │   ├── models.py
│   │   └── state.py
│   └── providers/
│       └── jobs_ch/
│           ├── analytics.py
│           ├── cli.py
│           ├── client.py
│           ├── detail.py
│           ├── extractors.py
│           └── service.py
├── market_analytics/
│   ├── __init__.py
│   ├── analytics.py
│   ├── constants.py
│   ├── io.py
│   ├── reporting.py
│   └── skills.py
├── scripts/
│   └── export_analytics.py
├── tests/
│   └── test_market_analytics.py
├── streamlit_app.py
└── pyproject.toml
```

## Architecture

- `swiss_jobs/core`: source-agnostic parser runtime pieces shared by all providers
- `swiss_jobs/providers/jobs_ch`: jobs.ch-specific HTTP, extraction, enrichment, and provider assets
- `runtime/jobs_ch`: generated provider runtime files and SQLite databases
- `market_analytics`: dataset-level analytics and Streamlit dashboard code

No SQLite migration was required for this restructuring. The existing schema already stores
`source`, shared vacancy fields, and per-run state, so it remains valid for future providers.

## Expected dataset columns

The analytics code standardizes common aliases into these canonical columns:

- `company`
- `role_category`
- `city`
- `canton`
- `seniority`
- `work_mode`
- `skills`

Supported aliases include fields such as `company_name`, `role_family_primary`, `place`,
`state`, `seniority_level`, `remote_mode`, `detected_skills`, and `keywords_matched`.

## Run

Install dependencies:

```bash
python3 -m pip install -e .
python3 -m pip install -e '.[dashboard]'
```

Export analytics as CSV:

```bash
python3 scripts/export_analytics.py /path/to/processed_dataset.csv --output-dir analytics_output
```

If you do not already have a processed dataset file, first run the built-in `jobs.ch`
parser through the generic provider CLI:

```bash
python3 -m swiss_jobs.cli.parse --source jobs_ch --config swiss_jobs/providers/jobs_ch/configs/config_info.json
```

This creates a database at:

```text
runtime/jobs_ch/config-info/jobs_ch.sqlite
```

The analytics script can read that SQLite database directly:

```bash
python3 scripts/export_analytics.py runtime/jobs_ch/config-info/jobs_ch.sqlite --output-dir analytics_output
```

Run tests:

```bash
python3 -m unittest tests/providers/jobs_ch/test_jobs_ch_analytics.py tests/providers/jobs_ch/test_jobs_ch_service.py tests/test_market_analytics.py tests/test_swiss_jobs_structure.py
```

Run the optional dashboard:

```bash
streamlit run streamlit_app.py
```

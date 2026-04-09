# Swiss IT Job Market Analytics

Dataset analytics for a processed `jobs.ch` vacancy dataset.

## Suggested file tree

```text
.
├── jobs_ch/
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
parser. It writes vacancies into a local SQLite database:

```bash
python3 jobs_ch/main.py --config jobs_ch/configs/config_info.json
```

This creates a database at:

```text
jobs_ch/runtime/config-info/jobs_ch.sqlite
```

The analytics script can read that SQLite database directly:

```bash
python3 scripts/export_analytics.py jobs_ch/runtime/config-info/jobs_ch.sqlite --output-dir analytics_output
```

Run tests:

```bash
python3 -m unittest tests/test_market_analytics.py
```

Run the optional dashboard:

```bash
streamlit run streamlit_app.py
```

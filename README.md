# Swiss IT Jobs Analytics

Current sources:

- `jobs.ch`
- `jobscout24.ch`
- `jobup.ch`

## Install

```bash
python3 -m pip install -e .
```

Frontend tooling:

```bash
cd site
npm install
```

## Collect vacancies

Run all providers:

```bash
python3 -m swiss_jobs.cli.parse --all-sources --mode new
```

Provider-specific examples:

```bash
python3 -m swiss_jobs.cli.parse \
  --source jobs_ch \
  --config swiss_jobs/providers/jobs_ch/configs/config_info.json
```

```bash
python3 -m swiss_jobs.cli.parse \
  --source jobscout24_ch \
  --config swiss_jobs/providers/jobscout24_ch/configs/config_info.json
```

```bash
python3 -m swiss_jobs.cli.parse \
  --source jobup_ch \
  --config swiss_jobs/providers/jobup_ch/configs/config_info.json
```

## Local analytics export

Generate analytics CSV files from one or more processed dataset snapshots:

```bash
python3 scripts/export_analytics.py \
  runtime/jobs_ch/main-config/jobs_ch.sqlite \
  runtime/jobscout24_ch/main-config/jobscout24_ch.sqlite \
  runtime/jobup_ch/main-config/jobup_ch.sqlite \
  --output-dir analytics_output
```

Build compact public snapshots from the generated CSV files:

```bash
python3 scripts/build_public_stats.py \
  --csv-dir analytics_output \
  --output-dir public_stats/data \
  --copy-csv-dir public_stats/csv
```

The repository can carry a committed public snapshot in:

- `public_stats/data/` for JSON consumed by the frontend
- `public_stats/csv/` for public-safe CSV exports

Only aggregated public data is committed there. SQLite databases and raw vacancy descriptions are not published.

## Public site

The GitHub Pages frontend lives in `site/` and reads only JSON snapshots from `public_stats/data/`.

Local frontend development:

```bash
cd site
npm run dev
```

Production build:

```bash
cd site
npm run build
```

## GitHub Pages publication

Workflow:

- `.github/workflows/build_public_stats.yml`

Default behavior:

- if `public_stats/data/metadata.json` is already committed, the workflow deploys that committed public snapshot
- if you provide `dataset_paths`, the workflow rebuilds analytics and snapshots first, then deploys the new result

How to enable Pages:

1. Push the repository to GitHub.
2. Open `Settings` → `Pages`.
3. Set the source to `GitHub Actions`.

How to deploy:

1. Open `Actions` → `Build and Deploy Public Site`.
2. Click `Run workflow`.
3. Leave `dataset_paths` empty to deploy the committed public snapshot, or provide repo-relative dataset files to rebuild first.
4. Open the deployed Pages URL or download the `public-stats` artifact.

## Quick first run

If you want a faster test run without detail pages:

```bash
python3 -m swiss_jobs.cli.parse \
  --source jobscout24_ch \
  --config swiss_jobs/providers/jobscout24_ch/configs/config_info.json \
  --skip-detail-schema \
  --max-pages 1
```

```bash
python3 -m swiss_jobs.cli.parse \
  --source jobs_ch \
  --config swiss_jobs/providers/jobs_ch/configs/config_info.json \
  --skip-detail-schema \
  --max-pages 1
```

```bash
python3 -m swiss_jobs.cli.parse \
  --source jobup_ch \
  --config swiss_jobs/providers/jobup_ch/configs/config_info.json \
  --skip-detail-schema \
  --max-pages 1
```

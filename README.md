# Swiss IT Jobs Analytics

Current sources:

- `jobs.ch`
- `jobscout24.ch`
- `jobup.ch`

## Install

```bash
python3 -m pip install -e .
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

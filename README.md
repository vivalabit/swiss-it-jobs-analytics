# Swiss IT Jobs Analytics

Swiss IT Jobs Analytics is a tool that analyzes thousands of job postings across the Swiss market to identify the most in-demand skills, technologies, and career paths, helping you understand what to learn today to stay competitive tomorrow.

Current sources:

- `jobs.ch`
- `jobscout24.ch`
- `jobup.ch`

The project is still in progress, so commands and structure may change.

The public site publishes aggregated snapshots of the Swiss IT job market built from processed vacancy datasets across multiple job boards. It highlights broad signals such as vacancy volume, employer activity, skill demand, geographic concentration, seniority mix, and work mode distribution.


## Install

```bash
python3 -m pip install -r requirements.txt
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
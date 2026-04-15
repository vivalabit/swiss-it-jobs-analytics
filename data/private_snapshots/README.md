# Private Snapshot Inputs

Put repository-local source snapshots here when you want the GitHub Actions workflow to build public stats without passing manual paths.

Supported formats:

- `.csv`
- `.parquet`
- `.json`
- `.jsonl`
- `.sqlite`
- `.db`

This directory is an input area only. Its contents are not part of the public web output.

Committed smoke-test fixture:

- `sample_public_stats_dataset.csv`

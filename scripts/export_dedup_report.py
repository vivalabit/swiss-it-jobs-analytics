from __future__ import annotations

import argparse
from pathlib import Path

from market_analytics.analytics import exclude_staffing_agencies
from market_analytics.deduplication import build_cross_source_dedup_report
from market_analytics.io import load_and_validate_datasets


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export cross-source deduplication matches from processed vacancy datasets.",
    )
    parser.add_argument(
        "dataset_paths",
        nargs="+",
        type=Path,
        help="One or more dataset paths (CSV, Parquet, SQLite, JSON, JSONL).",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("analytics_output/cross_source_dedup_report.csv"),
        help="CSV file where duplicate match rows will be written.",
    )
    parser.add_argument(
        "--include-staffing-agencies",
        action="store_true",
        help="Keep staffing agencies in the deduplication report instead of aligning with public analytics.",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    dataset = load_and_validate_datasets(args.dataset_paths)
    if not args.include_staffing_agencies:
        dataset = exclude_staffing_agencies(dataset).reset_index(drop=True)
    report = build_cross_source_dedup_report(dataset)

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(args.output_path, index=False)

    duplicate_groups = (
        int(report["duplicate_group_id"].nunique()) if "duplicate_group_id" in report.columns else 0
    )
    duplicate_rows = int(len(report))
    print(f"Processed {len(dataset)} vacancies from {len(args.dataset_paths)} dataset(s).")
    print(f"Found {duplicate_groups} cross-source duplicate groups covering {duplicate_rows} rows.")
    print(args.output_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

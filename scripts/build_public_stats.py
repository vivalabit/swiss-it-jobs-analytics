from __future__ import annotations

import argparse
from pathlib import Path

from market_analytics.public_snapshots import build_public_snapshots


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build compact public JSON snapshots from analytics CSV outputs.",
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=Path("analytics_output"),
        help="Directory containing analytics CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public_stats/data"),
        help="Directory where JSON snapshots will be written.",
    )
    parser.add_argument(
        "--copy-csv-dir",
        type=Path,
        default=Path("public_stats/csv"),
        help="Directory where source analytics CSV files will be copied.",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    snapshot_paths = build_public_snapshots(
        csv_dir=args.csv_dir,
        output_dir=args.output_dir,
        copy_csv_dir=args.copy_csv_dir,
    )
    print(f"Built {len(snapshot_paths)} public snapshot files in {args.output_dir.resolve()}")
    for path in snapshot_paths:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

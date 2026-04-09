from __future__ import annotations

import argparse
from pathlib import Path

from market_analytics.io import load_and_validate_dataset
from market_analytics.reporting import build_analytics_outputs, save_analytics_outputs


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Swiss IT job market analytics CSV outputs from a processed dataset.",
    )
    parser.add_argument("dataset_path", type=Path, help="Path to the processed dataset.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analytics_output"),
        help="Directory where analytics CSV files will be written.",
    )
    parser.add_argument(
        "--top-skills",
        type=int,
        default=20,
        help="Maximum number of skills to keep in top skill tables.",
    )
    parser.add_argument(
        "--top-pairs",
        type=int,
        default=50,
        help="Maximum number of skill co-occurrence pairs to keep.",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    dataset = load_and_validate_dataset(args.dataset_path)
    outputs = build_analytics_outputs(
        dataset=dataset,
        top_skills_limit=args.top_skills,
        top_skill_pairs_limit=args.top_pairs,
    )
    saved_paths = save_analytics_outputs(outputs, args.output_dir)

    print(f"Processed {len(dataset)} vacancies.")
    print(f"Saved {len(saved_paths)} analytics files to {args.output_dir.resolve()}")
    for path in saved_paths:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

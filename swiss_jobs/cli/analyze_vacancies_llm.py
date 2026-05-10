from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from swiss_jobs.core.llm_analysis import (
    DEFAULT_OPENAI_MODEL,
    OpenAIVacancyAnalyzer,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASES = {
    "jobs_ch": PROJECT_ROOT / "runtime" / "jobs_ch" / "main-config" / "jobs_ch.sqlite",
    "jobscout24_ch": PROJECT_ROOT
    / "runtime"
    / "jobscout24_ch"
    / "main-config"
    / "jobscout24_ch.sqlite",
    "jobup_ch": PROJECT_ROOT / "runtime" / "jobup_ch" / "main-config" / "jobup_ch.sqlite",
    "linked_in": PROJECT_ROOT / "runtime" / "linked_in" / "main-config" / "linked_in.sqlite",
    "swissdevjobs_ch": PROJECT_ROOT
    / "runtime"
    / "swissdevjobs_ch"
    / "main-config"
    / "swissdevjobs_ch.sqlite",
}
SOURCE_TO_DB_VALUE = {
    "jobs_ch": "jobs.ch",
    "jobscout24_ch": "jobscout24.ch",
    "jobup_ch": "jobup.ch",
    "linked_in": "LinkedIn",
    "swissdevjobs_ch": "swissdevjobs.ch",
}


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = _strip_dotenv_value(value.strip())
        os.environ[key] = value


def _strip_dotenv_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value.split(" #", 1)[0].strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run OpenAI-based enrichment for vacancies stored in a local SQLite database."
    )
    parser.add_argument(
        "--source",
        choices=sorted(DEFAULT_DATABASES),
        default="swissdevjobs_ch",
        help="Provider source to analyze.",
    )
    parser.add_argument(
        "--database-path",
        default="",
        help="Override SQLite path. Defaults to the runtime database for the selected source.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_OPENAI_MODEL,
        help="OpenAI model id to use. Default: gpt-5-nano.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="How many vacancies to process. Default: 5.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N matching vacancies.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Analyze all matching vacancies instead of using --limit.",
    )
    parser.add_argument(
        "--include-analyzed",
        action="store_true",
        help="Include vacancies that already have saved LLM analysis.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write results back to the database, only print sample output.",
    )
    parser.add_argument(
        "--estimate-cost",
        action="store_true",
        help="Only estimate token usage and cost for the selected vacancy set.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable progress logging in stderr.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = build_parser()
    args = parser.parse_args(argv)

    database_path = Path(args.database_path) if args.database_path else DEFAULT_DATABASES[args.source]
    source_value = SOURCE_TO_DB_VALUE[args.source]
    limit = None if args.all else max(args.limit, 0)

    analyzer = OpenAIVacancyAnalyzer(
        model=args.model,
        progress_logger=None if args.quiet else _progress_logger,
    )

    if args.estimate_cost:
        estimate = analyzer.estimate_cost(
            str(database_path),
            limit=limit,
            offset=args.offset,
            only_missing=not args.include_analyzed,
        )
        payload = {
            "database_path": str(database_path),
            "source": source_value,
            "model": estimate.model,
            "vacancy_count": estimate.vacancy_count,
            "estimated_input_tokens": estimate.estimated_input_tokens,
            "estimated_output_tokens": estimate.estimated_output_tokens,
            "estimated_total_cost_usd": estimate.estimated_total_cost_usd,
            "estimated_cost_per_vacancy_usd": estimate.estimated_cost_per_vacancy_usd,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    stats, previews = analyzer.analyze_database(
        str(database_path),
        limit=limit,
        offset=args.offset,
        only_missing=not args.include_analyzed,
        dry_run=args.dry_run,
    )
    payload = {
        "database_path": str(database_path),
        "source": source_value,
        "model": args.model,
        "processed": stats.processed,
        "updated": stats.updated,
        "failed": stats.failed,
        "input_tokens": stats.input_tokens,
        "output_tokens": stats.output_tokens,
        "estimated_total_cost_usd": round(stats.total_cost_usd, 6),
        "dry_run": args.dry_run,
        "results": previews,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _progress_logger(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())

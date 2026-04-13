from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from swiss_jobs.core.models import ClientConfig, ClientRunResult, ConfigValidationError
from swiss_jobs.providers.jobup_ch.service import JobupChParserService, slugify_runtime_name

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME_DIR = str(PROJECT_ROOT / "runtime" / "jobup_ch")


def load_json_config(path: str) -> dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read config file '{path}': {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in config file '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Config root must be a JSON object")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse jobup Switzerland vacancies into a local SQLite database."
    )
    parser.add_argument("--config", default="", help="JSON config path for a single run profile")
    parser.add_argument(
        "--mode",
        choices=["new", "search"],
        default="new",
        help="new: latest vacancies, search: term/location search page",
    )
    parser.add_argument(
        "--canton",
        default="",
        help="Swiss canton code, e.g. zh. Used to set default search locations.",
    )
    parser.add_argument("--term", default="", help="Search term (for --mode search)")
    parser.add_argument(
        "--terms",
        action="append",
        default=[],
        help="Multiple terms (comma separated or repeated)",
    )
    parser.add_argument("--location", default="", help="Location (for --mode search), e.g. zurich")
    parser.add_argument(
        "--locations",
        action="append",
        default=[],
        help="Multiple locations (comma separated or repeated)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="How many pages to scan (0 = all pages)",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Include token (can be used multiple times)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exclude token (can be used multiple times)",
    )
    parser.add_argument("--json", action="store_true", help="Print run output as JSON")
    parser.add_argument(
        "--output-format",
        choices=["full", "brief"],
        default="",
        help="Returned output payload format",
    )
    parser.add_argument(
        "--no-state",
        action="store_true",
        help="Disable seen-ID tracking (print all found jobs)",
    )
    parser.add_argument("--database-path", default="", help="SQLite database path for run storage")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Save current results into state and print nothing",
    )
    parser.add_argument("--watch", type=int, default=0, help="Polling interval in seconds. 0 = run once")
    parser.add_argument(
        "--skip-detail-schema",
        action="store_true",
        help="Skip vacancy detail enrichment",
    )
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=0,
        help="Max vacancies per run for detail page fetch (0 = no limit)",
    )
    parser.add_argument(
        "--detail-workers",
        type=int,
        default=8,
        help="Parallel workers for vacancy detail fetching",
    )
    parser.add_argument("--no-progress", action="store_true", help="Hide progress logs in stderr")
    parser.add_argument(
        "--role-keywords",
        action="append",
        default=[],
        help="Target role keywords (comma separated or repeated)",
    )
    parser.add_argument(
        "--seniority-keywords",
        action="append",
        default=[],
        help="Target seniority keywords (comma separated or repeated)",
    )
    parser.add_argument(
        "--require-role-and-seniority",
        action="store_true",
        help="Require BOTH role and seniority match",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Disable archive-style vacancy storage in the database",
    )
    parser.add_argument(
        "--no-new-jobs",
        action="store_true",
        help="Disable new-job markers in the database",
    )
    return parser


def _runtime_defaults(defaults: argparse.Namespace) -> dict[str, Any]:
    return {
        "mode": defaults.mode,
        "canton": defaults.canton,
        "term": defaults.term,
        "terms": list(defaults.terms),
        "location": defaults.location,
        "locations": list(defaults.locations),
        "max_pages": defaults.max_pages,
        "include": list(defaults.include),
        "exclude": list(defaults.exclude),
        "json": defaults.json,
        "database_path": defaults.database_path,
        "bootstrap": defaults.bootstrap,
        "watch": defaults.watch,
        "skip_detail_schema": defaults.skip_detail_schema,
        "detail_limit": defaults.detail_limit,
        "detail_workers": defaults.detail_workers,
        "no_progress": defaults.no_progress,
        "role_keywords": list(defaults.role_keywords),
        "seniority_keywords": list(defaults.seniority_keywords),
        "require_role_and_seniority": defaults.require_role_and_seniority,
        "no_archive": defaults.no_archive,
        "no_new_jobs": defaults.no_new_jobs,
        "no_state": defaults.no_state,
    }


def _collect_cli_overrides(
    args: argparse.Namespace,
    defaults: argparse.Namespace,
) -> dict[str, Any]:
    excluded = {"config"}
    overrides: dict[str, Any] = {}
    for key, value in vars(args).items():
        if key in excluded:
            continue
        if value != getattr(defaults, key):
            overrides[key] = value
    return overrides


def _build_config(args: argparse.Namespace, defaults: argparse.Namespace) -> ClientConfig:
    payload = _runtime_defaults(defaults)
    file_config: dict[str, Any] = {}
    if args.config:
        file_config = load_json_config(args.config)

    payload.update(file_config)
    payload.update(_collect_cli_overrides(args, defaults))
    payload.setdefault("database_path", _resolve_database_path(args))
    payload.setdefault("client_id", "main-config")
    payload.setdefault("name", "main-config")
    return ClientConfig.from_dict(
        payload,
        source=args.config or "<cli>",
        default_client_id="main-config",
    )


def _resolve_database_path(args: argparse.Namespace) -> str:
    if args.database_path:
        return str(Path(args.database_path))
    if args.config:
        config_path = Path(args.config).resolve()
        runtime_name = slugify_runtime_name(config_path.stem)
    else:
        runtime_name = "main-config"
    return str(Path(DEFAULT_RUNTIME_DIR) / runtime_name / "jobup_ch.sqlite")


def _print_text_jobs(jobs: list[dict[str, Any]]) -> None:
    for idx, job in enumerate(jobs, start=1):
        posted = job.get("posted_at") or job.get("publication_date") or "-"
        company = job.get("company") or "-"
        location = job.get("location") or job.get("place") or "-"
        title = job.get("title") or "-"
        url = job.get("url") or "-"
        print(f"{idx}. [{posted}] {title}")
        print(f"   {company} | {location}")
        print(f"   {url}")


def _print_single_result(result: ClientRunResult, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.output_jobs, ensure_ascii=False, indent=2))
        return
    _print_text_jobs(result.output_jobs)


def _report_result_issues(result: ClientRunResult) -> None:
    for warning in result.warnings:
        print(f"[warn] {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"[error] {error}", file=sys.stderr)


def _run_with_watch(service: JobupChParserService, config: ClientConfig) -> int:
    while True:
        result = service.run(config)
        _report_result_issues(result)
        if result.output_jobs:
            _print_single_result(result, as_json=config.json_output)
            print("")
        time.sleep(config.watch)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    defaults = parser.parse_args([])
    args = parser.parse_args(argv)

    service = JobupChParserService()
    try:
        config = _build_config(args, defaults)
    except (ValueError, ConfigValidationError) as exc:
        print(f"[config error] {exc}", file=sys.stderr)
        return 2

    if config.watch == 0:
        result = service.run(config)
        _report_result_issues(result)
        _print_single_result(result, as_json=config.json_output)
        return 0 if result.success else 1

    return _run_with_watch(service, config)


if __name__ == "__main__":
    raise SystemExit(main())

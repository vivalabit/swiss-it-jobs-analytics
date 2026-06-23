from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable

from . import local_web_server as _local_web_server
from . import resume_matcher as _resume_matcher
from . import static as _static
from .local_web_server import (
    AI_ANALYSIS_RUNS,
    AI_ANALYSIS_RUNS_LOCK,
    FACET_TERM_TYPES,
    MAX_RUN_LOGS,
    PARSER_RUNS,
    PARSER_RUNS_LOCK,
    PROJECT_ROOT,
    PUBLIC_STATS_RUNS,
    PUBLIC_STATS_RUNS_LOCK,
    SEARCH_DEFAULT_PAGE_SIZE,
    SEARCH_MAX_PAGE_SIZE,
    SOURCE_DATABASE_PATHS,
    TECH_TERM_TYPES,
    LocalSearchConfig,
    _analysis_cli_args,
    _analysis_command,
    _browser_open_url as _server_browser_open_url,
    _local_ipv4_addresses as _server_local_ipv4_addresses,
    _parser_cli_args,
    _parser_command,
    _public_stats_command_plan,
    _public_stats_options,
    get_ai_analysis_run,
    get_parser_run,
    get_public_stats_run,
    load_facets,
    search_local_databases,
    serve,
    start_ai_analysis_run,
    start_parser_run,
    start_public_stats_run,
    update_openai_settings,
)
from .resume_matcher import build_resume_pdf_bytes, build_tailored_resume_cv, build_tailored_resume_pdf, fetch_external_vacancy, requests
from .search_vacancies import DEFAULT_RUNTIME_DATABASES, _resolve_database_paths
from .static import STATIC_CACHE_CONTROL, _static_asset, render_index

_local_ipv4_addresses = _server_local_ipv4_addresses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a local read-only web search UI for stored vacancy SQLite databases.",
    )
    parser.add_argument(
        "--database-path",
        action="append",
        default=[],
        help="SQLite database path. Can be repeated. Defaults to existing runtime/*/main-config/*.sqlite files.",
    )
    parser.add_argument("--host", help="Bind host. Defaults to 127.0.0.1, or 0.0.0.0 with --share-lan.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port. Defaults to 8765.")
    parser.add_argument("--open", action="store_true", help="Open the page in the default browser.")
    parser.add_argument(
        "--share-lan",
        action="store_true",
        help="Allow other devices on the same trusted local network to open the app.",
    )
    return parser


def _display_urls(host: str, port: int) -> list[str]:
    if host in {"0.0.0.0", "::", ""}:
        urls = [f"http://127.0.0.1:{port}/"]
        urls.extend(f"http://{address}:{port}/" for address in _local_ipv4_addresses())
        return urls
    return [f"http://{host}:{port}/"]


def _browser_open_url(host: str, port: int) -> str:
    return _server_browser_open_url(host, port)


def __getattr__(name: str) -> Any:
    for module in (_local_web_server, _resume_matcher, _static):
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def build_resume_match(
    database_paths: Iterable[Path],
    payload: dict[str, Any],
    *,
    openai_transport: Any | None = None,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    original_fetch = _resume_matcher.fetch_external_vacancy
    _resume_matcher.fetch_external_vacancy = fetch_external_vacancy
    try:
        return _resume_matcher.build_resume_match(
            database_paths,
            payload,
            openai_transport=openai_transport,
            openai_api_key=openai_api_key,
        )
    finally:
        _resume_matcher.fetch_external_vacancy = original_fetch


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        database_paths = tuple(_resolve_database_paths(args.database_path))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not database_paths:
        defaults = ", ".join(str(path) for path in DEFAULT_RUNTIME_DATABASES)
        print(f"error: no local databases found. Checked: {defaults}", file=sys.stderr)
        return 2

    host = args.host or ("0.0.0.0" if args.share_lan else "127.0.0.1")
    serve(
        LocalSearchConfig(database_paths=database_paths, host=host, port=args.port),
        open_browser=args.open,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

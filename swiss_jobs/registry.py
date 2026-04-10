from __future__ import annotations

from collections.abc import Callable

from .providers.jobs_ch.cli import main as jobs_ch_cli_main
from .providers.jobs_ch.service import JobsChParserService, run_jobs_ch_parser

CLI_ENTRYPOINTS: dict[str, Callable[[list[str] | None], int]] = {
    "jobs_ch": jobs_ch_cli_main,
}

RUNNERS: dict[str, Callable[..., object]] = {
    "jobs_ch": run_jobs_ch_parser,
}

SERVICES: dict[str, type[object]] = {
    "jobs_ch": JobsChParserService,
}


def list_supported_sources() -> list[str]:
    return sorted(CLI_ENTRYPOINTS)


def get_cli_entrypoint(source: str) -> Callable[[list[str] | None], int]:
    try:
        return CLI_ENTRYPOINTS[source]
    except KeyError as exc:
        supported = ", ".join(list_supported_sources())
        raise ValueError(f"Unsupported source '{source}'. Supported sources: {supported}") from exc

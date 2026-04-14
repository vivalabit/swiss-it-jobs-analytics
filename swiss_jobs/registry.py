from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path

from .providers.jobs_ch.cli import main as jobs_ch_cli_main
from .providers.jobs_ch.service import JobsChParserService, run_jobs_ch_parser
from .providers.jobscout24_ch.cli import main as jobscout24_ch_cli_main
from .providers.jobscout24_ch.service import (
    JobScout24ChParserService,
    run_jobscout24_ch_parser,
)
from .providers.jobup_ch.cli import main as jobup_ch_cli_main
from .providers.jobup_ch.service import JobupChParserService, run_jobup_ch_parser


@dataclass(frozen=True, slots=True)
class SourceInfo:
    key: str
    display_name: str
    domain: str
    description: str
    default_config_path: str

CLI_ENTRYPOINTS: dict[str, Callable[[list[str] | None], int]] = {
    "jobs_ch": jobs_ch_cli_main,
    "jobscout24_ch": jobscout24_ch_cli_main,
    "jobup_ch": jobup_ch_cli_main,
}

RUNNERS: dict[str, Callable[..., object]] = {
    "jobs_ch": run_jobs_ch_parser,
    "jobscout24_ch": run_jobscout24_ch_parser,
    "jobup_ch": run_jobup_ch_parser,
}

SERVICES: dict[str, type[object]] = {
    "jobs_ch": JobsChParserService,
    "jobscout24_ch": JobScout24ChParserService,
    "jobup_ch": JobupChParserService,
}

SOURCE_INFO: dict[str, SourceInfo] = {
    "jobs_ch": SourceInfo(
        key="jobs_ch",
        display_name="jobs.ch",
        domain="www.jobs.ch",
        description="Swiss Jobs portal",
        default_config_path=str(
            Path(__file__).resolve().parent / "providers" / "jobs_ch" / "configs" / "config_info.json"
        ),
    ),
    "jobscout24_ch": SourceInfo(
        key="jobscout24_ch",
        display_name="jobscout24.ch",
        domain="www.jobscout24.ch",
        description="Swiss JobScout24 portal",
        default_config_path=str(
            Path(__file__).resolve().parent / "providers" / "jobscout24_ch" / "configs" / "config_info.json"
        ),
    ),
    "jobup_ch": SourceInfo(
        key="jobup_ch",
        display_name="jobup.ch",
        domain="www.jobup.ch",
        description="Swiss Jobup portal",
        default_config_path=str(
            Path(__file__).resolve().parent / "providers" / "jobup_ch" / "configs" / "config_info.json"
        ),
    ),
}


def list_supported_sources() -> list[str]:
    return sorted(CLI_ENTRYPOINTS)


def get_cli_entrypoint(source: str) -> Callable[[list[str] | None], int]:
    try:
        return CLI_ENTRYPOINTS[source]
    except KeyError as exc:
        supported = ", ".join(list_supported_sources())
        raise ValueError(f"Unsupported source '{source}'. Supported sources: {supported}") from exc


def get_source_info(source: str) -> SourceInfo:
    try:
        return SOURCE_INFO[source]
    except KeyError as exc:
        supported = ", ".join(list_supported_sources())
        raise ValueError(f"Unsupported source '{source}'. Supported sources: {supported}") from exc

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from swiss_jobs.core.archive import make_run_id, utc_now_iso
from swiss_jobs.core.database import JobsDatabase
from swiss_jobs.core.filters import (
    evaluate_role_seniority_filters,
    normalize_tokens,
    passes_text_filters,
)
from swiss_jobs.core.formatter import format_vacancies
from swiss_jobs.core.models import ClientConfig, ClientRunResult, ParserStats, VacancyFull
from swiss_jobs.core.state import compute_new_ids

from swiss_jobs.providers.jobs_ch.analytics import build_job_analytics

from .client import LinkedInHttpClient

CANTON_TO_LOCATIONS = {
    "ag": ["Aargau, Switzerland"],
    "ai": ["Appenzell Innerrhoden, Switzerland"],
    "ar": ["Appenzell Ausserrhoden, Switzerland"],
    "be": ["Bern, Switzerland"],
    "bl": ["Basel-Landschaft, Switzerland"],
    "bs": ["Basel, Switzerland"],
    "fr": ["Fribourg, Switzerland"],
    "ge": ["Geneva, Switzerland"],
    "gl": ["Glarus, Switzerland"],
    "gr": ["Graubunden, Switzerland"],
    "ju": ["Jura, Switzerland"],
    "lu": ["Lucerne, Switzerland"],
    "ne": ["Neuchatel, Switzerland"],
    "nw": ["Nidwalden, Switzerland"],
    "ow": ["Obwalden, Switzerland"],
    "sg": ["St Gallen, Switzerland"],
    "sh": ["Schaffhausen, Switzerland"],
    "so": ["Solothurn, Switzerland"],
    "sz": ["Schwyz, Switzerland"],
    "tg": ["Thurgau, Switzerland"],
    "ti": ["Ticino, Switzerland"],
    "ur": ["Uri, Switzerland"],
    "vd": ["Vaud, Switzerland"],
    "vs": ["Valais, Switzerland"],
    "zg": ["Zug, Switzerland"],
    "zh": ["Zurich, Switzerland"],
}


def slugify_runtime_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "default"


class LinkedInParserService:
    def __init__(
        self,
        *,
        http_client: Any | None = None,
        runtime_root: str | Path | None = None,
    ) -> None:
        self.http_client = http_client or LinkedInHttpClient()
        self.runtime_root = (
            Path(runtime_root)
            if runtime_root
            else Path(__file__).resolve().parents[3] / "runtime" / "linked_in"
        )

    def run(self, run_config: ClientConfig | Mapping[str, Any]) -> ClientRunResult:
        config = self._coerce_config(run_config)
        return self._run_config(config)

    def _coerce_config(self, run_config: ClientConfig | Mapping[str, Any]) -> ClientConfig:
        if isinstance(run_config, ClientConfig):
            payload = run_config.to_dict()
        else:
            payload = dict(run_config)
        payload.setdefault(
            "database_path",
            str(
                self.runtime_root
                / slugify_runtime_name(payload.get("client_id") or "main-config")
                / "linked_in.sqlite"
            ),
        )
        return ClientConfig.from_dict(
            payload,
            source=payload.get("client_config_path") or "<runtime>",
            default_client_id=payload.get("client_id") or "main-config",
        )

    def _run_config(self, config: ClientConfig) -> ClientRunResult:
        timestamp = utc_now_iso()
        run_id = make_run_id(timestamp)
        stats = ParserStats()
        result = ClientRunResult(
            run_id=run_id,
            client_id=config.client_id,
            timestamp=timestamp,
            effective_config=config,
            stats=stats,
        )
        try:
            queries = config.build_queries(CANTON_TO_LOCATIONS)
            stats.total_queries = len(queries)

            vacancies, warnings, successful_queries = self.http_client.search(config, queries)
            result.warnings.extend(warnings)
            stats.successful_queries = successful_queries
            if not vacancies and successful_queries == 0:
                raise RuntimeError(
                    "LinkedIn is unreachable for all queries (network/proxy/authentication or temporary blocking)."
                )

            stats.total_fetched = len(vacancies)
            text_filtered = [
                vacancy
                for vacancy in vacancies
                if passes_text_filters(
                    vacancy,
                    normalize_tokens(config.include),
                    normalize_tokens(config.exclude),
                )
            ]
            stats.after_text_filters = len(text_filtered)
            if not config.skip_detail_schema and text_filtered:
                stats.detail_requested = True
                attempted, enriched = self.http_client.enrich_vacancies(
                    text_filtered,
                    detail_limit=config.detail_limit,
                    detail_workers=config.detail_workers,
                    show_progress=config.show_progress,
                )
                stats.detail_attempted = attempted
                stats.detail_enriched = enriched

            filtered = self._apply_role_filters(text_filtered, config)
            stats.after_role_filters = len(filtered)
            stats.filtered_out = stats.total_fetched - stats.after_role_filters

            new_ids, seen_ids = self._compute_state(config, filtered)

            for vacancy in filtered:
                analytics = build_job_analytics(vacancy)
                if analytics:
                    vacancy.extra["analytics"] = analytics
                else:
                    vacancy.extra.pop("analytics", None)

            result.all_jobs_full = filtered
            result.new_jobs_full = [
                vacancy for vacancy in filtered if vacancy.id in new_ids
            ]
            stats.new_jobs = len(result.new_jobs_full)

            result.output_jobs = format_vacancies(result.new_jobs_full, config.output_format)
            self._persist(config, result, seen_ids=seen_ids)
        except Exception as exc:
            result.errors.append(str(exc))
            result.output_jobs = []
            self._persist(config, result, seen_ids=[])
        return result

    def _apply_role_filters(
        self,
        vacancies: Sequence[VacancyFull],
        config: ClientConfig,
    ) -> list[VacancyFull]:
        role_keywords = normalize_tokens(config.role_keywords)
        seniority_keywords = normalize_tokens(config.seniority_keywords)

        result: list[VacancyFull] = []
        for vacancy in vacancies:
            decision = evaluate_role_seniority_filters(
                vacancy,
                role_keywords=role_keywords,
                seniority_keywords=seniority_keywords,
                require_both=config.require_role_and_seniority,
            )
            vacancy.role_match = decision.role_match
            vacancy.seniority_match = decision.seniority_match
            vacancy.keywords_matched = list(decision.matched_keywords)
            if decision.passes:
                result.append(vacancy)
        return result

    def _compute_state(
        self,
        config: ClientConfig,
        vacancies: Sequence[VacancyFull],
    ) -> tuple[set[str], list[str]]:
        if not config.use_state:
            ids = [vacancy.id for vacancy in vacancies if vacancy.id]
            return set(ids), ids

        database = JobsDatabase(self._resolve_database_path(config))
        seen_ids = database.load_seen_ids(config.client_id)
        new_ids, updated_seen = compute_new_ids(
            vacancies,
            seen_ids,
            bootstrap=config.bootstrap,
        )
        return new_ids, updated_seen

    def _persist(self, config: ClientConfig, result: ClientRunResult, *, seen_ids: Sequence[str]) -> None:
        database_path = self._resolve_database_path(config)
        database = JobsDatabase(database_path)
        result.database_path = str(database_path)
        database.persist_result(config, result)
        if not result.errors and config.use_state:
            database.mark_seen(config.client_id, seen_ids, result.timestamp)

    def _resolve_database_path(self, config: ClientConfig) -> Path:
        if config.database_path:
            return Path(config.database_path)
        if config.client_config_path:
            stem = Path(config.client_config_path).stem or config.client_id
            return self.runtime_root / slugify_runtime_name(stem) / "linked_in.sqlite"
        return self.runtime_root / slugify_runtime_name(config.client_id) / "linked_in.sqlite"


def run_linked_in_parser(run_config: ClientConfig | Mapping[str, Any]) -> ClientRunResult:
    return LinkedInParserService().run(run_config)


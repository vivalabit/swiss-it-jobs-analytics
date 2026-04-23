from __future__ import annotations

import json
import re
import sqlite3
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
from swiss_jobs.core.models import ClientConfig, ClientRunResult, ParserStats, QuerySpec, VacancyFull
from swiss_jobs.core.state import compute_new_ids

from swiss_jobs.providers.jobs_ch.analytics import build_job_analytics

from .client import LinkedInHttpClient

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "configs" / "config_info.json"
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


def build_linkedin_queries(config: ClientConfig) -> list[QuerySpec]:
    if config.mode == "new":
        return [QuerySpec(term="", location="", index=1, total=1)]

    terms = config.effective_terms()
    locations = _effective_linkedin_locations(config)
    if config.canton and not locations:
        locations = [item for item in CANTON_TO_LOCATIONS.get(config.canton, []) if item]
    if not locations:
        locations = ["Switzerland"]

    pairs = [(term, location) for term in terms for location in locations]
    total = len(pairs)
    return [
        QuerySpec(term=term, location=location, index=index, total=total)
        for index, (term, location) in enumerate(pairs, start=1)
    ]


def _effective_linkedin_locations(config: ClientConfig) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_value in [config.location, *config.locations]:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _has_explicit_seniority_metadata(vacancy: VacancyFull) -> bool:
    raw = vacancy.raw or {}
    for key in ("seniority", "seniority_level", "job_seniority_level", "seniorityLevel"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return True

    detail_attributes = raw.get("detailAttributes")
    if isinstance(detail_attributes, Mapping):
        value = detail_attributes.get("seniorityLevel")
        if isinstance(value, str) and value.strip():
            return True
    return False


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

    def open_login_session(self, run_config: ClientConfig | Mapping[str, Any]) -> None:
        config = self._coerce_config(run_config)
        self.http_client.open_login_session(config)

    def _coerce_config(self, run_config: ClientConfig | Mapping[str, Any]) -> ClientConfig:
        if isinstance(run_config, ClientConfig):
            payload = run_config.to_dict()
        else:
            payload = dict(run_config)
        explicit_csv_path = bool(payload.get("csv_path"))
        explicit_json_path = bool(payload.get("json_path"))

        if DEFAULT_CONFIG_PATH.is_file():
            defaults = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(defaults, dict):
                merged_payload = dict(defaults)
                merged_payload.update(payload)
                payload = merged_payload

        if explicit_csv_path and not explicit_json_path:
            payload["json_path"] = ""
        if explicit_json_path and not explicit_csv_path:
            payload["csv_path"] = ""

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
            queries = build_linkedin_queries(config)
            stats.total_queries = len(queries)

            vacancies, warnings, successful_queries = self.http_client.search(config, queries)
            result.warnings.extend(warnings)
            stats.successful_queries = successful_queries
            if not vacancies and successful_queries == 0:
                raise RuntimeError(
                    "LinkedIn CSV provider did not load any vacancy rows."
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
            if vacancy.seniority_match is None:
                vacancy.seniority_match = _has_explicit_seniority_metadata(vacancy)
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
        migrate_legacy_linkedin_ids(database_path)
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


def migrate_legacy_linkedin_ids(database_path: Path) -> None:
    if not database_path.is_file():
        return

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "vacancies"):
            return
        rows = connection.execute(
            """
            SELECT vacancy_id
            FROM vacancies
            WHERE source = 'linkedin.com'
              AND vacancy_id NOT LIKE 'linkedin:%'
            """
        ).fetchall()
        for row in rows:
            legacy_id = str(row["vacancy_id"])
            if not legacy_id:
                continue
            new_id = f"linkedin:{legacy_id}"
            _rename_vacancy_id(connection, legacy_id, new_id)
        connection.commit()
    finally:
        connection.close()


def _rename_vacancy_id(connection: sqlite3.Connection, old_id: str, new_id: str) -> None:
    existing = connection.execute(
        "SELECT 1 FROM vacancies WHERE vacancy_id = ?",
        (new_id,),
    ).fetchone()
    if existing:
        _execute_if_table_exists(connection, "run_vacancies", "DELETE FROM run_vacancies WHERE vacancy_id = ?", old_id)
        _execute_if_table_exists(
            connection,
            "client_seen_vacancies",
            "DELETE FROM client_seen_vacancies WHERE vacancy_id = ?",
            old_id,
        )
        _execute_if_table_exists(connection, "vacancy_terms", "DELETE FROM vacancy_terms WHERE vacancy_id = ?", old_id)
        connection.execute("DELETE FROM vacancies WHERE vacancy_id = ?", (old_id,))
        return

    connection.execute(
        "UPDATE vacancies SET vacancy_id = ? WHERE vacancy_id = ?",
        (new_id, old_id),
    )
    _execute_if_table_exists(
        connection,
        "run_vacancies",
        "UPDATE run_vacancies SET vacancy_id = ? WHERE vacancy_id = ?",
        new_id,
        old_id,
    )
    _execute_if_table_exists(
        connection,
        "client_seen_vacancies",
        "UPDATE client_seen_vacancies SET vacancy_id = ? WHERE vacancy_id = ?",
        new_id,
        old_id,
    )
    _execute_if_table_exists(
        connection,
        "vacancy_terms",
        "UPDATE vacancy_terms SET vacancy_id = ? WHERE vacancy_id = ?",
        new_id,
        old_id,
    )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _execute_if_table_exists(
    connection: sqlite3.Connection,
    table_name: str,
    sql: str,
    *params: str,
) -> None:
    if _table_exists(connection, table_name):
        connection.execute(sql, params)

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

from swiss_jobs.core.database import ensure_database_schema
from swiss_jobs.core.salary import extract_salary_info
from swiss_jobs.core.models import VacancyFull

from .analytics import build_job_analytics
from .cli import load_json_config
from .client import JobsChHttpClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "swiss_jobs" / "providers" / "jobs_ch" / "configs" / "config_info.json"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "runtime" / "jobs_ch" / "main-config" / "jobs_ch.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill salary/detail fields for already stored jobs.ch vacancies.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Optional jobs_ch config JSON used to resolve defaults such as cookies_file.",
    )
    parser.add_argument(
        "--database-path",
        default=str(DEFAULT_DATABASE_PATH),
        help="SQLite database path with stored jobs.ch vacancies.",
    )
    parser.add_argument(
        "--cookies-file",
        default="",
        help="Optional Netscape cookies.txt file for authenticated detail requests.",
    )
    parser.add_argument(
        "--vacancy-id",
        action="append",
        default=[],
        help="Specific vacancy IDs to backfill. Can be repeated or comma separated.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit how many stored vacancies to process (0 = no limit).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel workers for detail fetch.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all stored jobs.ch vacancies, not only rows missing salary fields.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Hide progress logs in stderr.",
    )
    return parser


def backfill_database(
    database_path: str | Path,
    *,
    cookies_file: str | None = None,
    vacancy_ids: Iterable[str] = (),
    limit: int = 0,
    only_missing_salary: bool = True,
    workers: int = 8,
    show_progress: bool = True,
    http_client: Any | None = None,
) -> dict[str, int]:
    if workers < 1:
        raise ValueError("workers must be >= 1")

    path = Path(database_path)
    if not path.is_file():
        raise ValueError(f"Database file not found: {path}")

    vacancies = load_backfill_candidates(
        path,
        vacancy_ids=vacancy_ids,
        limit=limit,
        only_missing_salary=only_missing_salary,
    )
    if not vacancies:
        return {
            "selected": 0,
            "attempted": 0,
            "enriched": 0,
            "with_salary": 0,
            "errors": 0,
        }

    client = http_client or JobsChHttpClient()
    if hasattr(client, "configure_cookies"):
        client.configure_cookies(cookies_file=cookies_file, show_progress=show_progress)

    attempted, enriched = client.enrich_vacancies(
        vacancies,
        detail_limit=len(vacancies),
        detail_workers=workers,
        show_progress=show_progress,
    )

    with sqlite3.connect(path) as connection:
        ensure_database_schema(connection)
        for vacancy in vacancies:
            persist_backfilled_vacancy(connection, vacancy)
        connection.commit()

    with_salary = sum(1 for vacancy in vacancies if _has_salary(vacancy))
    errors = sum(1 for vacancy in vacancies if vacancy.detail_schema_error)
    return {
        "selected": len(vacancies),
        "attempted": attempted,
        "enriched": enriched,
        "with_salary": with_salary,
        "errors": errors,
    }


def load_backfill_candidates(
    database_path: Path,
    *,
    vacancy_ids: Iterable[str],
    limit: int,
    only_missing_salary: bool,
) -> list[VacancyFull]:
    ids = _split_csv_values(vacancy_ids)
    clauses = [
        "source = ?",
        "url IS NOT NULL",
        "trim(url) != ''",
    ]
    params: list[Any] = ["jobs.ch"]

    if only_missing_salary and not ids:
        clauses.append(
            """
            (
                salary_min IS NULL AND
                salary_max IS NULL AND
                COALESCE(trim(salary_text), '') = ''
            )
            """
        )

    if ids:
        placeholders = ", ".join("?" for _ in ids)
        clauses.append(f"vacancy_id IN ({placeholders})")
        params.extend(ids)

    query = f"""
        SELECT
            vacancy_id,
            source,
            title,
            company,
            place,
            publication_date,
            initial_publication_date,
            is_new,
            url,
            raw_json,
            description_html,
            description_text,
            job_posting_schema_json,
            detail_schema_error,
            detail_schema_skipped,
            role_match,
            seniority_match,
            keywords_matched_json
        FROM vacancies
        WHERE {" AND ".join(f"({clause.strip()})" for clause in clauses)}
        ORDER BY last_seen_at DESC, vacancy_id ASC
    """
    if limit > 0:
        query += f" LIMIT {int(limit)}"

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        ensure_database_schema(connection)
        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()

    return [_row_to_vacancy(row) for row in rows]


def persist_backfilled_vacancy(connection: sqlite3.Connection, vacancy: VacancyFull) -> None:
    salary = extract_salary_info(vacancy)
    analytics = build_job_analytics(vacancy) or {}
    connection.execute(
        """
        UPDATE vacancies
        SET
            raw_json = ?,
            description_html = ?,
            description_text = ?,
            job_posting_schema_json = ?,
            detail_schema_error = ?,
            detail_schema_skipped = ?,
            salary_min = ?,
            salary_max = ?,
            salary_currency = ?,
            salary_unit = ?,
            salary_text = ?,
            analytics_json = ?
        WHERE vacancy_id = ?
        """,
        (
            json.dumps(vacancy.raw, ensure_ascii=False, sort_keys=True),
            vacancy.description_html,
            vacancy.description_text,
            json.dumps(vacancy.job_posting_schema, ensure_ascii=False, sort_keys=True)
            if vacancy.job_posting_schema is not None
            else None,
            vacancy.detail_schema_error,
            1 if vacancy.detail_schema_skipped else 0,
            salary.minimum,
            salary.maximum,
            salary.currency,
            salary.unit,
            salary.text or salary.display_text,
            json.dumps(analytics, ensure_ascii=False, sort_keys=True),
            vacancy.id,
        ),
    )


def _row_to_vacancy(row: sqlite3.Row) -> VacancyFull:
    raw = _loads_json_object(row["raw_json"])
    keywords = _loads_json_list(row["keywords_matched_json"])
    schema = _loads_json_object(row["job_posting_schema_json"])
    return VacancyFull(
        id=str(row["vacancy_id"] or ""),
        title=str(row["title"] or ""),
        company=str(row["company"] or ""),
        place=str(row["place"] or ""),
        publication_date=row["publication_date"],
        initial_publication_date=row["initial_publication_date"],
        is_new=bool(row["is_new"]),
        url=str(row["url"] or ""),
        raw=raw,
        description_html=str(row["description_html"] or ""),
        description_text=str(row["description_text"] or ""),
        job_posting_schema=schema,
        detail_schema_error=row["detail_schema_error"],
        detail_schema_skipped=bool(row["detail_schema_skipped"]),
        role_match=_deserialize_optional_bool(row["role_match"]),
        seniority_match=_deserialize_optional_bool(row["seniority_match"]),
        keywords_matched=keywords,
        source=str(row["source"] or "jobs.ch"),
    )


def _loads_json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _loads_json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload if item is not None]


def _deserialize_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _split_csv_values(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for chunk in str(value).split(","):
            clean = chunk.strip()
            if clean:
                result.append(clean)
    return result


def _has_salary(vacancy: VacancyFull) -> bool:
    salary = extract_salary_info(vacancy)
    return any(
        value is not None and value != ""
        for value in (salary.minimum, salary.maximum, salary.currency, salary.unit, salary.text)
    )


def _resolve_cookies_file(args: argparse.Namespace) -> str | None:
    if args.cookies_file:
        return str(Path(args.cookies_file))
    config_path = Path(args.config) if args.config else None
    if config_path and config_path.is_file():
        config = load_json_config(str(config_path))
        value = config.get("cookies_file")
        if isinstance(value, str) and value.strip():
            return str(Path(value))
    return None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        stats = backfill_database(
            args.database_path,
            cookies_file=_resolve_cookies_file(args),
            vacancy_ids=args.vacancy_id,
            limit=args.limit,
            only_missing_salary=not args.all,
            workers=args.workers,
            show_progress=not args.no_progress,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.no_progress:
        print(
            (
                "[summary] jobs_ch salary backfill: "
                f"selected={stats['selected']} attempted={stats['attempted']} "
                f"enriched={stats['enriched']} with_salary={stats['with_salary']} "
                f"errors={stats['errors']}"
            ),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

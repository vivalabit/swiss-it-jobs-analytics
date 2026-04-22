from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_DATABASES = [
    PROJECT_ROOT / "runtime" / "jobs_ch" / "main-config" / "jobs_ch.sqlite",
    PROJECT_ROOT / "runtime" / "jobscout24_ch" / "main-config" / "jobscout24_ch.sqlite",
    PROJECT_ROOT / "runtime" / "jobup_ch" / "main-config" / "jobup_ch.sqlite",
    PROJECT_ROOT / "runtime" / "linked_in" / "main-config" / "linked_in.sqlite",
    PROJECT_ROOT / "runtime" / "swissdevjobs_ch" / "main-config" / "swissdevjobs_ch.sqlite",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search stored vacancies in local SQLite databases, including salary filters.",
    )
    parser.add_argument(
        "--database-path",
        action="append",
        default=[],
        help="SQLite database path. Can be repeated. Defaults to existing runtime/*/main-config/*.sqlite files.",
    )
    parser.add_argument(
        "--term",
        action="append",
        default=[],
        help="Text term to match in title/company/location/description. Can be repeated or comma separated.",
    )
    parser.add_argument("--source", action="append", default=[], help="Source filter, e.g. jobs.ch")
    parser.add_argument("--salary-min", type=int, default=None, help="Minimum desired salary")
    parser.add_argument("--salary-max", type=int, default=None, help="Maximum desired salary")
    parser.add_argument(
        "--salary-currency",
        default="",
        help="Salary currency filter, e.g. CHF",
    )
    parser.add_argument(
        "--salary-unit",
        default="",
        help="Salary unit filter, e.g. YEAR or MONTH",
    )
    parser.add_argument(
        "--has-salary",
        action="store_true",
        help="Return only vacancies with any normalized salary value",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of vacancies to print",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of plain text",
    )
    return parser


def _split_csv_values(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for chunk in str(value).split(","):
            clean = chunk.strip()
            if clean:
                result.append(clean)
    return result


def _resolve_database_paths(cli_values: list[str]) -> list[Path]:
    explicit = [Path(value) for value in _split_csv_values(cli_values)]
    if explicit:
        missing = [path for path in explicit if not path.is_file()]
        if missing:
            missing_text = ", ".join(str(path) for path in missing)
            raise ValueError(f"Database file not found: {missing_text}")
        return explicit

    discovered = [path for path in DEFAULT_RUNTIME_DATABASES if path.is_file()]
    if not discovered:
        raise ValueError("No default runtime SQLite databases found. Pass --database-path explicitly.")
    return discovered


def _build_query(
    *,
    terms: list[str],
    sources: list[str],
    salary_min: int | None,
    salary_max: int | None,
    salary_currency: str,
    salary_unit: str,
    has_salary: bool,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if terms:
        for term in terms:
            clauses.append(
                """
                (
                    lower(title) LIKE ? OR
                    lower(company) LIKE ? OR
                    lower(place) LIKE ? OR
                    lower(description_text) LIKE ? OR
                    lower(salary_text) LIKE ?
                )
                """
            )
            pattern = f"%{term.lower()}%"
            params.extend([pattern, pattern, pattern, pattern, pattern])

    if sources:
        placeholders = ", ".join("?" for _ in sources)
        clauses.append(f"source IN ({placeholders})")
        params.extend(sources)

    if has_salary or salary_min is not None or salary_max is not None:
        clauses.append("(salary_min IS NOT NULL OR salary_max IS NOT NULL)")

    if salary_min is not None:
        clauses.append("COALESCE(salary_max, salary_min) >= ?")
        params.append(salary_min)

    if salary_max is not None:
        clauses.append("COALESCE(salary_min, salary_max) <= ?")
        params.append(salary_max)

    if salary_currency.strip():
        clauses.append("upper(COALESCE(salary_currency, '')) = ?")
        params.append(salary_currency.strip().upper())

    if salary_unit.strip():
        clauses.append("upper(COALESCE(salary_unit, '')) = ?")
        params.append(salary_unit.strip().upper())

    where_clause = ""
    if clauses:
        where_clause = "WHERE " + " AND ".join(f"({clause.strip()})" for clause in clauses)

    query = f"""
        SELECT
            vacancy_id,
            source,
            title,
            company,
            place,
            publication_date,
            initial_publication_date,
            url,
            salary_min,
            salary_max,
            salary_currency,
            salary_unit,
            salary_text,
            first_seen_at,
            last_seen_at
        FROM vacancies
        {where_clause}
        ORDER BY
            COALESCE(salary_max, salary_min) DESC,
            COALESCE(salary_min, salary_max) DESC,
            last_seen_at DESC,
            vacancy_id ASC
    """
    return query, params


def search_database(
    database_path: Path,
    *,
    terms: list[str],
    sources: list[str],
    salary_min: int | None,
    salary_max: int | None,
    salary_currency: str,
    salary_unit: str,
    has_salary: bool,
) -> list[dict[str, Any]]:
    query, params = _build_query(
        terms=terms,
        sources=sources,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        salary_unit=salary_unit,
        has_salary=has_salary,
    )
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()

    return [
        {
            "database_path": str(database_path),
            "id": str(row["vacancy_id"]),
            "source": row["source"],
            "title": row["title"],
            "company": row["company"],
            "location": row["place"],
            "publication_date": row["publication_date"],
            "initial_publication_date": row["initial_publication_date"],
            "url": row["url"],
            "salary_min": row["salary_min"],
            "salary_max": row["salary_max"],
            "salary_currency": row["salary_currency"],
            "salary_unit": row["salary_unit"],
            "salary_text": row["salary_text"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
        }
        for row in rows
    ]


def search_databases(
    database_paths: list[Path],
    *,
    terms: list[str],
    sources: list[str],
    salary_min: int | None,
    salary_max: int | None,
    salary_currency: str,
    salary_unit: str,
    has_salary: bool,
    limit: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for database_path in database_paths:
        results.extend(
            search_database(
                database_path,
                terms=terms,
                sources=sources,
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency=salary_currency,
                salary_unit=salary_unit,
                has_salary=has_salary,
            )
        )

    results.sort(
        key=lambda item: (
            item["salary_max"] if isinstance(item["salary_max"], int) else item["salary_min"] or -1,
            item["salary_min"] if isinstance(item["salary_min"], int) else item["salary_max"] or -1,
            str(item.get("last_seen_at") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    if limit > 0:
        return results[:limit]
    return results


def _format_salary(item: dict[str, Any]) -> str:
    salary_text = item.get("salary_text")
    if isinstance(salary_text, str) and salary_text.strip():
        return salary_text.strip()

    minimum = item.get("salary_min")
    maximum = item.get("salary_max")
    currency = str(item.get("salary_currency") or "").strip()
    unit = str(item.get("salary_unit") or "").strip()
    currency_prefix = f"{currency} " if currency else ""
    unit_suffix = f" / {unit.lower()}" if unit else ""

    if isinstance(minimum, int) and isinstance(maximum, int):
        if minimum == maximum:
            return f"{currency_prefix}{minimum}{unit_suffix}".strip()
        return f"{currency_prefix}{minimum}-{maximum}{unit_suffix}".strip()
    if isinstance(minimum, int):
        return f"{currency_prefix}{minimum}{unit_suffix}".strip()
    if isinstance(maximum, int):
        return f"{currency_prefix}{maximum}{unit_suffix}".strip()
    return "-"


def _print_text(results: list[dict[str, Any]]) -> None:
    for index, item in enumerate(results, start=1):
        print(f"{index}. [{item.get('source') or '-'}] {item.get('title') or '-'}")
        print(f"   {item.get('company') or '-'} | {item.get('location') or '-'}")
        print(f"   salary: {_format_salary(item)}")
        print(f"   last_seen: {item.get('last_seen_at') or '-'}")
        print(f"   db: {item.get('database_path') or '-'}")
        print(f"   {item.get('url') or '-'}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        database_paths = _resolve_database_paths(args.database_path)
        terms = _split_csv_values(args.term)
        sources = _split_csv_values(args.source)
        results = search_databases(
            database_paths,
            terms=terms,
            sources=sources,
            salary_min=args.salary_min,
            salary_max=args.salary_max,
            salary_currency=args.salary_currency,
            salary_unit=args.salary_unit,
            has_salary=args.has_salary,
            limit=args.limit,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_text(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

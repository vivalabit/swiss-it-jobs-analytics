from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Sequence

from .models import ClientConfig, ClientRunResult, VacancyFull
from .salary import extract_salary_info

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    config_path TEXT,
    database_path TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    success INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    errors_json TEXT NOT NULL,
    output_jobs_json TEXT NOT NULL,
    new_jobs_count INTEGER NOT NULL,
    total_jobs_count INTEGER NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

CREATE TABLE IF NOT EXISTS vacancies (
    vacancy_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT,
    company TEXT,
    place TEXT,
    publication_date TEXT,
    initial_publication_date TEXT,
    is_new INTEGER NOT NULL,
    url TEXT,
    employment_type TEXT,
    role_match INTEGER,
    seniority_match INTEGER,
    salary_min INTEGER,
    salary_max INTEGER,
    salary_currency TEXT,
    salary_unit TEXT,
    salary_text TEXT,
    keywords_matched_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    description_html TEXT NOT NULL,
    description_text TEXT NOT NULL,
    job_posting_schema_json TEXT,
    detail_schema_error TEXT,
    detail_schema_skipped INTEGER NOT NULL,
    analytics_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    first_run_id TEXT NOT NULL,
    last_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS client_seen_vacancies (
    client_id TEXT NOT NULL,
    vacancy_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (client_id, vacancy_id),
    FOREIGN KEY (client_id) REFERENCES clients(client_id),
    FOREIGN KEY (vacancy_id) REFERENCES vacancies(vacancy_id)
);

CREATE TABLE IF NOT EXISTS run_vacancies (
    run_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    vacancy_id TEXT NOT NULL,
    is_new_job INTEGER NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (run_id, vacancy_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (client_id) REFERENCES clients(client_id),
    FOREIGN KEY (vacancy_id) REFERENCES vacancies(vacancy_id)
);

CREATE TABLE IF NOT EXISTS vacancy_terms (
    vacancy_id TEXT NOT NULL,
    term_type TEXT NOT NULL,
    term_value TEXT NOT NULL,
    PRIMARY KEY (vacancy_id, term_type, term_value),
    FOREIGN KEY (vacancy_id) REFERENCES vacancies(vacancy_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_client_timestamp
ON runs (client_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_run_vacancies_client_run
ON run_vacancies (client_id, run_id);

CREATE INDEX IF NOT EXISTS idx_client_seen_vacancies_client
ON client_seen_vacancies (client_id);

CREATE INDEX IF NOT EXISTS idx_vacancy_terms_type_value
ON vacancy_terms (term_type, term_value);

"""

TERM_FIELDS = {
    "role_family_primary": "role_family_primary",
    "role_family_matches": "role_family",
    "seniority_labels": "seniority",
    "programming_languages": "programming_language",
    "frameworks_libraries": "framework_library",
    "cloud_platforms": "cloud_platform",
    "data_platforms": "data_platform",
    "databases": "database",
    "platforms": "platform",
    "tools": "tool",
    "vendors": "vendor",
    "protocols_standards": "protocol_standard",
    "methodologies": "methodology",
    "spoken_languages": "spoken_language",
    "employment_types": "employment_type",
    "occupational_categories": "occupational_category",
    "listing_tags": "listing_tag",
}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _coerce_term_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        clean = value.strip()
        return [clean] if clean else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result: list[str] = []
        for item in value:
            result.extend(_coerce_term_values(item))
        return result
    return []


def extract_term_rows(vacancy: VacancyFull) -> list[tuple[str, str]]:
    analytics = vacancy.extra.get("analytics")
    if not isinstance(analytics, dict):
        return []

    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for field_name, term_type in TERM_FIELDS.items():
        for raw_value in _coerce_term_values(analytics.get(field_name)):
            row = (term_type, raw_value)
            if row in seen:
                continue
            seen.add(row)
            rows.append(row)
    return rows


class JobsDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load_seen_ids(self, client_id: str) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT vacancy_id
                FROM client_seen_vacancies
                WHERE client_id = ?
                ORDER BY first_seen_at, vacancy_id
                """,
                (client_id,),
            ).fetchall()
        return [str(row["vacancy_id"]) for row in rows if row["vacancy_id"]]

    def mark_seen(self, client_id: str, vacancy_ids: Iterable[str], timestamp: str) -> None:
        values = [vacancy_id for vacancy_id in vacancy_ids if vacancy_id]
        if not values:
            return

        with self._connection() as connection:
            connection.executemany(
                """
                INSERT INTO client_seen_vacancies (client_id, vacancy_id, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(client_id, vacancy_id) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at
                """,
                [(client_id, vacancy_id, timestamp, timestamp) for vacancy_id in values],
            )

    def persist_result(self, config: ClientConfig, result: ClientRunResult) -> None:
        with self._connection() as connection:
            self._upsert_client(connection, config, str(self.path), result.timestamp)
            connection.execute(
                """
                INSERT INTO runs (
                    run_id,
                    client_id,
                    timestamp,
                    success,
                    config_json,
                    stats_json,
                    warnings_json,
                    errors_json,
                    output_jobs_json,
                    new_jobs_count,
                    total_jobs_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    client_id = excluded.client_id,
                    timestamp = excluded.timestamp,
                    success = excluded.success,
                    config_json = excluded.config_json,
                    stats_json = excluded.stats_json,
                    warnings_json = excluded.warnings_json,
                    errors_json = excluded.errors_json,
                    output_jobs_json = excluded.output_jobs_json,
                    new_jobs_count = excluded.new_jobs_count,
                    total_jobs_count = excluded.total_jobs_count
                """,
                (
                    result.run_id,
                    config.client_id,
                    result.timestamp,
                    0 if result.errors else 1,
                    _json_dumps(config.to_dict()),
                    _json_dumps(result.stats.to_dict()),
                    _json_dumps(result.warnings),
                    _json_dumps(result.errors),
                    _json_dumps(result.output_jobs),
                    len(result.new_jobs_full),
                    len(result.all_jobs_full),
                ),
            )

            if not result.errors:
                for vacancy in result.all_jobs_full:
                    self._upsert_vacancy(connection, vacancy, result)

                new_job_ids = {job.id for job in result.new_jobs_full}
                connection.execute(
                    "DELETE FROM run_vacancies WHERE run_id = ?",
                    (result.run_id,),
                )
                connection.executemany(
                    """
                    INSERT INTO run_vacancies (run_id, client_id, vacancy_id, is_new_job, position)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            result.run_id,
                            config.client_id,
                            vacancy.id,
                            1 if vacancy.id in new_job_ids else 0,
                            position,
                        )
                        for position, vacancy in enumerate(result.all_jobs_full, start=1)
                        if vacancy.id
                    ],
                )

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        ensure_database_schema(connection)
        return connection

    @contextmanager
    def _connection(self) -> sqlite3.Connection:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _upsert_client(
        self,
        connection: sqlite3.Connection,
        config: ClientConfig,
        database_path: str,
        timestamp: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO clients (client_id, name, config_path, database_path, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                name = excluded.name,
                config_path = excluded.config_path,
                database_path = excluded.database_path,
                updated_at = excluded.updated_at
            """,
            (
                config.client_id,
                config.name,
                config.client_config_path,
                database_path,
                timestamp,
            ),
        )

    def _upsert_vacancy(
        self,
        connection: sqlite3.Connection,
        vacancy: VacancyFull,
        result: ClientRunResult,
    ) -> None:
        salary_min, salary_max, salary_currency, salary_unit, salary_text = _extract_salary_columns(
            vacancy
        )
        existing = connection.execute(
            "SELECT first_seen_at, first_run_id FROM vacancies WHERE vacancy_id = ?",
            (vacancy.id,),
        ).fetchone()
        first_seen_at = str(existing["first_seen_at"]) if existing else result.timestamp
        first_run_id = str(existing["first_run_id"]) if existing else result.run_id

        connection.execute(
            """
            INSERT INTO vacancies (
                vacancy_id,
                source,
                title,
                company,
                place,
                publication_date,
                initial_publication_date,
                is_new,
                url,
                employment_type,
                role_match,
                seniority_match,
                salary_min,
                salary_max,
                salary_currency,
                salary_unit,
                salary_text,
                keywords_matched_json,
                raw_json,
                description_html,
                description_text,
                job_posting_schema_json,
                detail_schema_error,
                detail_schema_skipped,
                analytics_json,
                first_seen_at,
                last_seen_at,
                first_run_id,
                last_run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vacancy_id) DO UPDATE SET
                source = excluded.source,
                title = excluded.title,
                company = excluded.company,
                place = excluded.place,
                publication_date = excluded.publication_date,
                initial_publication_date = excluded.initial_publication_date,
                is_new = excluded.is_new,
                url = excluded.url,
                employment_type = excluded.employment_type,
                role_match = excluded.role_match,
                seniority_match = excluded.seniority_match,
                salary_min = excluded.salary_min,
                salary_max = excluded.salary_max,
                salary_currency = excluded.salary_currency,
                salary_unit = excluded.salary_unit,
                salary_text = excluded.salary_text,
                keywords_matched_json = excluded.keywords_matched_json,
                raw_json = excluded.raw_json,
                description_html = excluded.description_html,
                description_text = excluded.description_text,
                job_posting_schema_json = excluded.job_posting_schema_json,
                detail_schema_error = excluded.detail_schema_error,
                detail_schema_skipped = excluded.detail_schema_skipped,
                analytics_json = excluded.analytics_json,
                last_seen_at = excluded.last_seen_at,
                last_run_id = excluded.last_run_id
            """,
            (
                vacancy.id,
                vacancy.source,
                vacancy.title,
                vacancy.company,
                vacancy.place,
                vacancy.publication_date,
                vacancy.initial_publication_date,
                1 if vacancy.is_new else 0,
                vacancy.url,
                vacancy.employment_type,
                _serialize_bool(vacancy.role_match),
                _serialize_bool(vacancy.seniority_match),
                salary_min,
                salary_max,
                salary_currency,
                salary_unit,
                salary_text,
                _json_dumps(vacancy.keywords_matched),
                _json_dumps(vacancy.raw),
                vacancy.description_html,
                vacancy.description_text,
                _json_dumps(vacancy.job_posting_schema) if vacancy.job_posting_schema is not None else None,
                vacancy.detail_schema_error,
                1 if vacancy.detail_schema_skipped else 0,
                _json_dumps(vacancy.extra.get("analytics", {})),
                first_seen_at,
                result.timestamp,
                first_run_id,
                result.run_id,
            ),
        )

        connection.execute("DELETE FROM vacancy_terms WHERE vacancy_id = ?", (vacancy.id,))
        connection.executemany(
            """
            INSERT INTO vacancy_terms (vacancy_id, term_type, term_value)
            VALUES (?, ?, ?)
            """,
            [(vacancy.id, term_type, term_value) for term_type, term_value in extract_term_rows(vacancy)],
        )


def _serialize_bool(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def ensure_database_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    _ensure_vacancy_columns(connection)
    _ensure_vacancy_indexes(connection)


def _ensure_vacancy_columns(connection: sqlite3.Connection) -> None:
    existing = {
        str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
        for row in connection.execute("PRAGMA table_info(vacancies)").fetchall()
        if (row["name"] if isinstance(row, sqlite3.Row) else row[1])
    }
    for column_name, column_type in (
        ("salary_min", "INTEGER"),
        ("salary_max", "INTEGER"),
        ("salary_currency", "TEXT"),
        ("salary_unit", "TEXT"),
        ("salary_text", "TEXT"),
    ):
        if column_name not in existing:
            connection.execute(f"ALTER TABLE vacancies ADD COLUMN {column_name} {column_type}")


def _ensure_vacancy_indexes(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_vacancies_salary_filters
        ON vacancies (salary_currency, salary_unit, salary_min, salary_max)
        """
    )


def _extract_salary_columns(
    vacancy: VacancyFull,
) -> tuple[int | None, int | None, str | None, str | None, str | None]:
    salary = extract_salary_info(vacancy)
    return (
        salary.minimum,
        salary.maximum,
        salary.currency,
        salary.unit,
        salary.text,
    )

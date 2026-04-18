from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from swiss_jobs.core.database import JobsDatabase
from swiss_jobs.core.models import ClientConfig, ClientRunResult, VacancyFull

LEGACY_SCHEMA = """
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
"""


def make_config(database_path: Path) -> ClientConfig:
    return ClientConfig(
        client_id="client-a",
        name="client-a",
        database_path=str(database_path),
        output_format="brief",
    )


def make_result(config: ClientConfig, vacancy: VacancyFull) -> ClientRunResult:
    return ClientRunResult(
        run_id="run-1",
        client_id=config.client_id,
        timestamp="2026-04-18T10:00:00+02:00",
        effective_config=config,
        new_jobs_full=[vacancy],
        all_jobs_full=[vacancy],
        output_jobs=[],
    )


def make_swissdevjobs_vacancy() -> VacancyFull:
    return VacancyFull(
        id="salary-vacancy-1",
        title="DevOps Engineer",
        company="Acme",
        place="Zürich",
        publication_date="2026-04-15T08:33:05.175+02:00",
        initial_publication_date="2026-04-15T08:33:05.175+02:00",
        is_new=True,
        url="https://swissdevjobs.ch/jobs/salary-vacancy-1",
        source="swissdevjobs.ch",
        raw={
            "salary": {
                "currency": "CHF",
                "unit": "YEAR",
                "range": {
                    "minValue": 100000,
                    "maxValue": 130000,
                },
            },
            "salaryText": "CHF 100000 - 130000 / year",
        },
    )


class JobsDatabaseSalaryTests(unittest.TestCase):
    def test_persist_result_writes_normalized_salary_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancy = make_swissdevjobs_vacancy()

            JobsDatabase(database_path).persist_result(config, make_result(config, vacancy))

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT salary_min, salary_max, salary_currency, salary_unit, salary_text
                    FROM vacancies
                    WHERE vacancy_id = ?
                    """,
                    (vacancy.id,),
                ).fetchone()

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(100000, row[0])
            self.assertEqual(130000, row[1])
            self.assertEqual("CHF", row[2])
            self.assertEqual("YEAR", row[3])
            self.assertEqual("CHF 100000 - 130000 / year", row[4])

    def test_persist_result_migrates_legacy_vacancies_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "legacy.sqlite"
            with sqlite3.connect(database_path) as connection:
                connection.executescript(LEGACY_SCHEMA)

            config = make_config(database_path)
            vacancy = make_swissdevjobs_vacancy()

            JobsDatabase(database_path).persist_result(config, make_result(config, vacancy))

            with sqlite3.connect(database_path) as connection:
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(vacancies)").fetchall()
                }
                row = connection.execute(
                    """
                    SELECT salary_min, salary_max, salary_currency, salary_unit, salary_text
                    FROM vacancies
                    WHERE vacancy_id = ?
                    """,
                    (vacancy.id,),
                ).fetchone()

            self.assertTrue(
                {"salary_min", "salary_max", "salary_currency", "salary_unit", "salary_text"}.issubset(
                    columns
                )
            )
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(100000, row[0])
            self.assertEqual(130000, row[1])


if __name__ == "__main__":
    unittest.main()

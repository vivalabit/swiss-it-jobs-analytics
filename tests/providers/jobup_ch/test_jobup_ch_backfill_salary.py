from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from swiss_jobs.core.database import JobsDatabase
from swiss_jobs.core.models import ClientConfig, ClientRunResult, VacancyFull
from swiss_jobs.providers.jobup_ch.backfill_salary import backfill_database


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
        timestamp="2026-04-19T10:00:00+02:00",
        effective_config=config,
        new_jobs_full=[vacancy],
        all_jobs_full=[vacancy],
        output_jobs=[],
    )


class FakeBackfillClient:
    def configure_cookies(self, *, cookies_file, show_progress):  # noqa: ANN001
        self.cookies_file = cookies_file
        self.show_progress = show_progress

    def enrich_vacancies(self, vacancies, *, detail_limit, detail_workers, show_progress):  # noqa: ANN001
        for vacancy in vacancies:
            vacancy.job_posting_schema = {
                "@type": "JobPosting",
                "baseSalary": {
                    "currency": "CHF",
                    "value": {
                        "minValue": 90000,
                        "maxValue": 120000,
                        "unitText": "YEAR",
                    },
                },
            }
            vacancy.description_text = "Detailed description with salary."
            vacancy.detail_schema_error = None
            vacancy.detail_schema_skipped = False
        return len(vacancies), len(vacancies)


class JobupChBackfillSalaryTests(unittest.TestCase):
    def test_backfill_updates_existing_jobup_vacancy(self) -> None:
        vacancy = VacancyFull(
            id="old-jobup-1",
            title="Platform Engineer",
            company="Acme",
            place="Zurich",
            publication_date="2026-04-01",
            initial_publication_date="2026-04-01",
            is_new=False,
            url="https://www.jobup.ch/en/jobs/detail/old-jobup-1/",
            source="jobup.ch",
            raw={},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobup.sqlite"
            config = make_config(database_path)
            JobsDatabase(database_path).persist_result(config, make_result(config, vacancy))

            stats = backfill_database(
                database_path,
                cookies_file=None,
                http_client=FakeBackfillClient(),
                show_progress=False,
            )

            self.assertEqual(1, stats["selected"])
            self.assertEqual(1, stats["enriched"])
            self.assertEqual(1, stats["with_salary"])

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
            self.assertEqual(90000, row[0])
            self.assertEqual(120000, row[1])
            self.assertEqual("CHF", row[2])
            self.assertEqual("YEAR", row[3])
            self.assertEqual("CHF 90000-120000 / year", row[4])


if __name__ == "__main__":
    unittest.main()

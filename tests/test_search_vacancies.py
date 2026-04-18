from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from swiss_jobs.cli.search_vacancies import search_databases
from swiss_jobs.core.database import JobsDatabase
from swiss_jobs.core.models import ClientConfig, ClientRunResult, VacancyFull


def make_config(database_path: Path) -> ClientConfig:
    return ClientConfig(
        client_id="client-a",
        name="client-a",
        database_path=str(database_path),
        output_format="brief",
    )


def make_result(config: ClientConfig, vacancies: list[VacancyFull]) -> ClientRunResult:
    return ClientRunResult(
        run_id="run-1",
        client_id=config.client_id,
        timestamp="2026-04-18T10:00:00+02:00",
        effective_config=config,
        new_jobs_full=list(vacancies),
        all_jobs_full=list(vacancies),
        output_jobs=[],
    )


def make_vacancy(
    vacancy_id: str,
    *,
    title: str,
    minimum: int,
    maximum: int,
    currency: str = "CHF",
    unit: str = "YEAR",
) -> VacancyFull:
    return VacancyFull(
        id=vacancy_id,
        title=title,
        company="Acme",
        place="Zurich",
        publication_date="2026-04-15T08:33:05.175+02:00",
        initial_publication_date="2026-04-15T08:33:05.175+02:00",
        is_new=True,
        url=f"https://example.com/{vacancy_id}",
        source="jobs.ch",
        description_text=f"{title} vacancy",
        raw={
            "salary": {
                "currency": currency,
                "unit": unit,
                "range": {
                    "minValue": minimum,
                    "maxValue": maximum,
                },
            },
            "salaryText": f"{currency} {minimum} - {maximum} / {unit.lower()}",
        },
    )


class SearchVacanciesTests(unittest.TestCase):
    def test_search_databases_filters_by_salary_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            jobs = [
                make_vacancy("vacancy-1", title="Python Engineer", minimum=100000, maximum=130000),
                make_vacancy("vacancy-2", title="Junior QA", minimum=70000, maximum=85000),
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, jobs))

            results = search_databases(
                [database_path],
                terms=[],
                sources=[],
                salary_min=110000,
                salary_max=140000,
                salary_currency="CHF",
                salary_unit="YEAR",
                has_salary=False,
                limit=50,
            )

            self.assertEqual(["vacancy-1"], [item["id"] for item in results])
            self.assertEqual(100000, results[0]["salary_min"])
            self.assertEqual(130000, results[0]["salary_max"])

    def test_search_databases_combines_text_and_salary_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            jobs = [
                make_vacancy("vacancy-1", title="Python Engineer", minimum=100000, maximum=130000),
                make_vacancy("vacancy-2", title="Java Engineer", minimum=120000, maximum=140000),
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, jobs))

            results = search_databases(
                [database_path],
                terms=["python"],
                sources=["jobs.ch"],
                salary_min=90000,
                salary_max=None,
                salary_currency="CHF",
                salary_unit="YEAR",
                has_salary=False,
                limit=50,
            )

            self.assertEqual(["vacancy-1"], [item["id"] for item in results])


if __name__ == "__main__":
    unittest.main()

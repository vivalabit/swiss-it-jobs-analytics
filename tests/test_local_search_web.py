from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from swiss_jobs.cli.local_search_web import load_facets, search_local_databases
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
        timestamp="2026-06-01T10:00:00+02:00",
        effective_config=config,
        new_jobs_full=list(vacancies),
        all_jobs_full=list(vacancies),
        output_jobs=[],
    )


def make_vacancy(
    vacancy_id: str,
    *,
    title: str,
    company: str,
    place: str,
    salary_min: int | None = None,
    salary_max: int | None = None,
    analytics: dict[str, object],
) -> VacancyFull:
    raw = {}
    if salary_min is not None or salary_max is not None:
        raw = {
            "salary": {
                "currency": "CHF",
                "unit": "YEAR",
                "range": {
                    "minValue": salary_min,
                    "maxValue": salary_max,
                },
            },
        }

    return VacancyFull(
        id=vacancy_id,
        title=title,
        company=company,
        place=place,
        publication_date="2026-05-28T08:00:00+02:00",
        initial_publication_date="2026-05-28T08:00:00+02:00",
        is_new=True,
        url=f"https://example.com/{vacancy_id}",
        source="jobs.ch",
        description_text=f"{title} role with local database search.",
        raw=raw,
        extra={"analytics": analytics},
    )


class LocalSearchWebTests(unittest.TestCase):
    def test_search_local_databases_filters_by_terms_and_salary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancies = [
                make_vacancy(
                    "vacancy-1",
                    title="Python Backend Engineer",
                    company="Acme",
                    place="Zurich",
                    salary_min=120000,
                    salary_max=145000,
                    analytics={
                        "role_family_primary": "software_engineering",
                        "seniority_labels": ["senior"],
                        "programming_languages": ["python"],
                    },
                ),
                make_vacancy(
                    "vacancy-2",
                    title="Java QA Engineer",
                    company="Beta",
                    place="Bern",
                    salary_min=90000,
                    salary_max=105000,
                    analytics={
                        "role_family_primary": "quality_assurance",
                        "seniority_labels": ["mid"],
                        "programming_languages": ["java"],
                    },
                ),
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, vacancies))

            payload = search_local_databases(
                [database_path],
                {
                    "q": ["backend"],
                    "skill": ["python"],
                    "seniority": ["senior"],
                    "salary_min": ["110000"],
                    "limit": ["50"],
                },
            )

            self.assertEqual(["vacancy-1"], [item["id"] for item in payload["results"]])
            self.assertEqual([], payload["database_errors"])

    def test_search_local_databases_does_not_require_salary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancies = [
                make_vacancy(
                    "vacancy-1",
                    title="Python Engineer",
                    company="Acme",
                    place="Zurich",
                    analytics={
                        "role_family_primary": "software_engineering",
                        "programming_languages": ["python"],
                    },
                ),
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, vacancies))

            payload = search_local_databases(
                [database_path],
                {
                    "q": ["python"],
                    "limit": ["50"],
                },
            )

            self.assertEqual(["vacancy-1"], [item["id"] for item in payload["results"]])
            self.assertEqual("", payload["results"][0]["salary"])

    def test_load_facets_reads_local_database_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            JobsDatabase(database_path).persist_result(
                config,
                make_result(
                    config,
                    [
                        make_vacancy(
                            "vacancy-1",
                            title="Python Backend Engineer",
                            company="Acme",
                            place="Zurich",
                            salary_min=120000,
                            salary_max=145000,
                            analytics={
                                "role_family_primary": "software_engineering",
                                "seniority_labels": ["senior"],
                                "programming_languages": ["python"],
                            },
                        )
                    ],
                ),
            )

            facets = load_facets([database_path])

            self.assertEqual(1, facets["total"])
            self.assertEqual(
                [{"label": "jobs", "path": str(database_path), "count": 1}],
                facets["database_stats"],
            )
            self.assertEqual([{"value": "jobs.ch", "count": 1}], facets["sources"])
            self.assertIn({"value": "python", "count": 1}, facets["terms"]["programming_language"])


if __name__ == "__main__":
    unittest.main()

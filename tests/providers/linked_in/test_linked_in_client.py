from __future__ import annotations

import sqlite3
import tempfile
import unittest
import json
from pathlib import Path

from swiss_jobs.core.models import ClientConfig
from swiss_jobs.providers.linked_in.client import (
    LinkedInHttpClient,
    parse_vacancies_from_csv,
    parse_vacancies_from_json,
)
from swiss_jobs.providers.linked_in.service import LinkedInParserService, migrate_legacy_linkedin_ids


class LinkedInClientTests(unittest.TestCase):
    def test_csv_rows_are_mapped_to_linkedin_vacancies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "linkedin.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "job_id,job_title,company_name,job_location,url,description,employment_type,remote,job_posted_date",
                        "4211112222,Software Engineer,Acme AG,\"Zurich, Switzerland\",https://www.linkedin.com/jobs/view/4211112222/,Python and PostgreSQL,Full-time,Hybrid,2026-04-20",
                    ]
                ),
                encoding="utf-8",
            )

            jobs, warnings = parse_vacancies_from_csv(csv_path)

        self.assertEqual([], warnings)
        self.assertEqual(1, len(jobs))
        self.assertEqual("linkedin:4211112222", jobs[0].id)
        self.assertEqual("Software Engineer", jobs[0].title)
        self.assertEqual("Acme AG", jobs[0].company)
        self.assertEqual("Zurich, Switzerland", jobs[0].place)
        self.assertEqual("Full-time", jobs[0].employment_type)
        self.assertIn("Python", jobs[0].description_text)
        self.assertEqual("Full-time", jobs[0].raw["employmentType"])
        self.assertEqual("Hybrid", jobs[0].raw["workplace"])

    def test_search_input_csv_is_not_imported_as_vacancies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "input.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "location,keyword,country,time_range,job_type,experience_level",
                        "switzerland,software engineer,CH,Any time,,",
                    ]
                ),
                encoding="utf-8",
            )

            jobs, warnings = parse_vacancies_from_csv(csv_path)

        self.assertEqual([], jobs)
        self.assertEqual(1, len(warnings))
        self.assertIn("search-input rows", warnings[0])

    def test_json_records_are_mapped_to_linkedin_vacancies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "linkedin.json"
            json_path.write_text(
                json.dumps(
                    [
                        {
                            "url": "https://www.linkedin.com/jobs/view/backend-entwickler-80-100%25-at-fincons-group-4395046745",
                            "job_posting_id": "4395046745",
                            "job_title": "Backend Entwickler 80 - 100%",
                            "company_name": "Fincons Group",
                            "job_location": "Bern, Berne, Switzerland",
                            "job_summary": "Mehrjährige Erfahrung in der Backend-Entwicklung mit Java, Spring Boot, PostgreSQL, DevOps und Scrum.",
                            "job_seniority_level": "Mid-Senior level",
                            "job_employment_type": "Full-time",
                            "job_industries": "Wireless Services, Telecommunications",
                            "company_url": "https://it.linkedin.com/company/fincons-group",
                            "job_posted_time": "3 weeks ago",
                            "job_num_applicants": 25,
                            "company_logo": "https://media.licdn.com/logo.png",
                            "job_posted_date": "2026-04-02T08:40:30.428Z",
                            "job_description_formatted": "<p>Java and Spring Boot with PostgreSQL.</p>",
                            "base_salary": None,
                            "is_easy_apply": True,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            jobs, warnings = parse_vacancies_from_json(json_path)

        self.assertEqual([], warnings)
        self.assertEqual(1, len(jobs))
        vacancy = jobs[0]
        self.assertEqual("linkedin:4395046745", vacancy.id)
        self.assertEqual("Backend Entwickler 80 - 100%", vacancy.title)
        self.assertEqual("Fincons Group", vacancy.company)
        self.assertEqual("Bern, Berne, Switzerland", vacancy.place)
        self.assertEqual("2026-04-02", vacancy.publication_date)
        self.assertEqual("Full-time", vacancy.employment_type)
        self.assertIn("Java", vacancy.description_text)
        self.assertEqual("Mid-Senior level", vacancy.raw["detailAttributes"]["seniorityLevel"])
        self.assertEqual("25", vacancy.raw["detailAttributes"]["applicantCountText"])
        self.assertEqual(["Wireless Services", "Telecommunications"], vacancy.job_posting_schema["industry"])
        self.assertEqual(
            "https://it.linkedin.com/company/fincons-group",
            vacancy.job_posting_schema["hiringOrganization"]["sameAs"],
        )

    def test_client_loads_csv_once_without_queries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "linkedin.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "title,company,location,description",
                        "Backend Engineer,Example AG,\"Bern, Switzerland\",Build APIs with Python",
                    ]
                ),
                encoding="utf-8",
            )
            config = ClientConfig.from_dict(
                {"mode": "search", "csv_path": str(csv_path)},
                source="<test>",
            )

            jobs, warnings, successful = LinkedInHttpClient().search(config, [])

        self.assertEqual(1, successful)
        self.assertEqual([], warnings)
        self.assertEqual(1, len(jobs))
        self.assertTrue(jobs[0].id.startswith("linkedin:csv-2-"))

    def test_client_prefers_json_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "linkedin.json"
            json_path.write_text(
                json.dumps([{"job_posting_id": "1", "job_title": "Data Engineer"}]),
                encoding="utf-8",
            )
            config = ClientConfig.from_dict(
                {"mode": "search", "json_path": str(json_path)},
                source="<test>",
            )

            jobs, warnings, successful = LinkedInHttpClient().search(config, [])

        self.assertEqual(1, successful)
        self.assertEqual([], warnings)
        self.assertEqual("linkedin:1", jobs[0].id)

    def test_service_persists_csv_vacancy_with_analytics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            csv_path = tmp_path / "linkedin.csv"
            database_path = tmp_path / "linked_in.sqlite"
            csv_path.write_text(
                "\n".join(
                    [
                        "job_id,job_title,company_name,job_location,description,employment_type",
                        "4211112222,Senior Python Engineer,Acme AG,\"Zurich, Switzerland\",Build Python services and APIs,Full-time",
                    ]
                ),
                encoding="utf-8",
            )

            result = LinkedInParserService(runtime_root=tmp_path).run(
                {
                    "mode": "search",
                    "csv_path": str(csv_path),
                    "database_path": str(database_path),
                    "no_state": True,
                    "role_keywords": ["python engineer", "software engineer"],
                    "output_format": "full",
                }
            )

            self.assertTrue(result.success, result.errors)
            connection = sqlite3.connect(database_path)
            try:
                row = connection.execute(
                    "SELECT title, employment_type, description_text, analytics_json FROM vacancies"
                ).fetchone()
            finally:
                connection.close()

        self.assertIsNotNone(row)
        self.assertEqual("Senior Python Engineer", row[0])
        self.assertEqual("Full-time", row[1])
        self.assertIn("Python", row[2])
        self.assertIn("programming_languages", row[3])

    def test_legacy_linkedin_ids_are_namespaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "linked_in.sqlite"
            connection = sqlite3.connect(database_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE vacancies (vacancy_id TEXT PRIMARY KEY, source TEXT NOT NULL);
                    CREATE TABLE run_vacancies (run_id TEXT, client_id TEXT, vacancy_id TEXT, is_new_job INTEGER, position INTEGER);
                    CREATE TABLE client_seen_vacancies (client_id TEXT, vacancy_id TEXT, first_seen_at TEXT, last_seen_at TEXT);
                    CREATE TABLE vacancy_terms (vacancy_id TEXT, term_type TEXT, term_value TEXT);
                    INSERT INTO vacancies VALUES ('4400525309', 'linkedin.com');
                    INSERT INTO run_vacancies VALUES ('run-1', 'client-a', '4400525309', 1, 1);
                    INSERT INTO client_seen_vacancies VALUES ('client-a', '4400525309', 'ts', 'ts');
                    INSERT INTO vacancy_terms VALUES ('4400525309', 'role_family', 'software');
                    """
                )
                connection.commit()
            finally:
                connection.close()

            migrate_legacy_linkedin_ids(database_path)

            connection = sqlite3.connect(database_path)
            try:
                self.assertEqual(
                    [("linkedin:4400525309",)],
                    connection.execute("SELECT vacancy_id FROM vacancies").fetchall(),
                )
                self.assertEqual(
                    [("linkedin:4400525309",)],
                    connection.execute("SELECT vacancy_id FROM run_vacancies").fetchall(),
                )
                self.assertEqual(
                    [("linkedin:4400525309",)],
                    connection.execute("SELECT vacancy_id FROM client_seen_vacancies").fetchall(),
                )
                self.assertEqual(
                    [("linkedin:4400525309",)],
                    connection.execute("SELECT vacancy_id FROM vacancy_terms").fetchall(),
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()

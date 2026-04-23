from __future__ import annotations

import sqlite3
import tempfile
import unittest
import json
from pathlib import Path

from swiss_jobs.core.models import ClientConfig
from swiss_jobs.providers.linked_in.cli import build_parser, _build_config
from swiss_jobs.providers.linked_in.client import (
    LinkedInHttpClient,
    parse_vacancies_from_csv,
    parse_vacancies_from_json,
)
from swiss_jobs.providers.linked_in.service import LinkedInParserService, migrate_legacy_linkedin_ids
from swiss_jobs.providers.linked_in.statistics import rebuild_runtime_statistics


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
        self.assertTrue(jobs[0].id.startswith("linkedin:fallback-"))

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

    def test_cli_loads_bundled_role_keyword_defaults(self) -> None:
        parser = build_parser()
        defaults = parser.parse_args([])
        args = parser.parse_args([])

        config = _build_config(args, defaults)

        self.assertIn("backend entwickler", config.role_keywords)
        self.assertIn("softwareentwickler", config.role_keywords)

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

    def test_service_persists_json_seniority_into_analytics_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            json_path = tmp_path / "linkedin.json"
            database_path = tmp_path / "linked_in.sqlite"
            json_path.write_text(
                json.dumps(
                    [
                        {
                            "job_posting_id": "4395046745",
                            "job_title": "Backend Entwickler 80 - 100%",
                            "company_name": "Fincons Group",
                            "job_location": "Bern, Berne, Switzerland",
                            "job_summary": "Mehrjährige Erfahrung in der Backend-Entwicklung mit Java, Spring Boot und PostgreSQL.",
                            "job_seniority_level": "Mid-Senior level",
                            "job_employment_type": "Full-time",
                            "job_posted_date": "2026-04-02T08:40:30.428Z",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = LinkedInParserService(runtime_root=tmp_path).run(
                {
                    "mode": "search",
                    "json_path": str(json_path),
                    "database_path": str(database_path),
                    "no_state": True,
                    "output_format": "full",
                }
            )

            self.assertTrue(result.success, result.errors)
            connection = sqlite3.connect(database_path)
            try:
                analytics_row = connection.execute(
                    "SELECT analytics_json FROM vacancies WHERE vacancy_id = 'linkedin:4395046745'"
                ).fetchone()
                term_rows = connection.execute(
                    "SELECT term_type, term_value FROM vacancy_terms WHERE vacancy_id = 'linkedin:4395046745' ORDER BY term_type, term_value"
                ).fetchall()
            finally:
                connection.close()

        self.assertIsNotNone(analytics_row)
        analytics = json.loads(analytics_row[0])
        self.assertEqual(["mid", "senior"], analytics["seniority_labels"])
        self.assertIn(("seniority", "mid"), term_rows)
        self.assertIn(("seniority", "senior"), term_rows)
        self.assertTrue(result.all_jobs_full[0].seniority_match)

    def test_service_uses_bundled_role_keyword_defaults_for_json_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            json_path = tmp_path / "linkedin.json"
            database_path = tmp_path / "linked_in.sqlite"
            json_path.write_text(
                json.dumps(
                    [
                        {
                            "job_posting_id": "4395046745",
                            "job_title": "Backend Entwickler 80 - 100%",
                            "company_name": "Fincons Group",
                            "job_location": "Bern, Berne, Switzerland",
                            "job_summary": "Backend-Entwicklung mit Java und Spring Boot.",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = LinkedInParserService(runtime_root=tmp_path).run(
                {
                    "mode": "search",
                    "json_path": str(json_path),
                    "database_path": str(database_path),
                    "no_state": True,
                    "output_format": "full",
                }
            )

        self.assertTrue(result.success, result.errors)
        self.assertEqual(1, len(result.all_jobs_full))
        self.assertTrue(result.all_jobs_full[0].role_match)
        self.assertIn("backend entwickler", result.all_jobs_full[0].keywords_matched)

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

    def test_idless_json_rows_keep_stable_ids_across_reimports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            json_path = tmp_path / "linkedin.json"
            database_path = tmp_path / "linked_in.sqlite"

            first_payload = [
                {
                    "job_title": "Platform Engineer",
                    "company_name": "Acme AG",
                    "job_location": "Zurich, Switzerland",
                    "url": "https://www.linkedin.com/jobs/view/platform-engineer-at-acme-ag",
                    "job_posted_date": "2026-04-20",
                    "job_summary": "Build platform tooling with Python.",
                }
            ]
            second_payload = [
                {
                    "job_posting_id": "4400000001",
                    "job_title": "Backend Engineer",
                    "company_name": "Beta AG",
                    "job_location": "Bern, Switzerland",
                    "job_posted_date": "2026-04-21",
                    "job_summary": "Build backend services with Java.",
                },
                first_payload[0],
            ]

            json_path.write_text(json.dumps(first_payload, ensure_ascii=False), encoding="utf-8")
            first_result = LinkedInParserService(runtime_root=tmp_path).run(
                {
                    "mode": "search",
                    "json_path": str(json_path),
                    "database_path": str(database_path),
                    "output_format": "full",
                }
            )

            json_path.write_text(json.dumps(second_payload, ensure_ascii=False), encoding="utf-8")
            second_result = LinkedInParserService(runtime_root=tmp_path).run(
                {
                    "mode": "search",
                    "json_path": str(json_path),
                    "database_path": str(database_path),
                    "output_format": "full",
                }
            )

            self.assertTrue(first_result.success, first_result.errors)
            self.assertTrue(second_result.success, second_result.errors)

            connection = sqlite3.connect(database_path)
            try:
                stored_ids = {
                    row[0] for row in connection.execute("SELECT vacancy_id FROM vacancies").fetchall()
                }
            finally:
                connection.close()

        self.assertEqual(2, len(stored_ids))
        self.assertIn("linkedin:4400000001", stored_ids)
        fallback_ids = [vacancy_id for vacancy_id in stored_ids if vacancy_id.startswith("linkedin:fallback-")]
        self.assertEqual(1, len(fallback_ids))

    def test_rebuild_runtime_statistics_dedupes_runtime_datasets(self) -> None:
        analytics_json = json.dumps(
            {
                "role_family_primary": "software_engineering",
                "seniority_labels": ["mid"],
                "remote_mode": "hybrid",
                "job_location": {"locality": "Zurich", "region": "ZH"},
                "programming_languages": ["python"],
                "frameworks_libraries": ["fastapi"],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            database_a = tmp_path / "linked_in_a.sqlite"
            database_b = tmp_path / "linked_in_b.sqlite"
            analytics_output = tmp_path / "analytics_output"
            public_data = tmp_path / "public_stats" / "data"
            public_csv = tmp_path / "public_stats" / "csv"

            database_rows = {
                database_a: [("linkedin:1", "linkedin.com", "Python Engineer")],
                database_b: [
                    ("linkedin:1", "linkedin.com", "Python Engineer"),
                    ("jobs:2", "jobs.ch", "Java Engineer"),
                ],
            }

            for database_path, rows in database_rows.items():
                connection = sqlite3.connect(database_path)
                try:
                    connection.execute(
                        """
                        CREATE TABLE vacancies (
                            vacancy_id TEXT PRIMARY KEY,
                            source TEXT,
                            title TEXT,
                            company TEXT,
                            place TEXT,
                            publication_date TEXT,
                            first_seen_at TEXT,
                            last_seen_at TEXT,
                            description_text TEXT,
                            analytics_json TEXT,
                            salary_min INTEGER,
                            salary_max INTEGER,
                            salary_currency TEXT,
                            salary_unit TEXT,
                            salary_text TEXT
                        )
                        """
                    )
                    connection.executemany(
                        """
                        INSERT INTO vacancies (
                            vacancy_id,
                            source,
                            title,
                            company,
                            place,
                            publication_date,
                            first_seen_at,
                            last_seen_at,
                            description_text,
                            analytics_json,
                            salary_min,
                            salary_max,
                            salary_currency,
                            salary_unit,
                            salary_text
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                vacancy_id,
                                source,
                                title,
                                "Acme AG",
                                "Zurich, Switzerland",
                                "2026-04-21",
                                "2026-04-21T08:00:00+00:00",
                                "2026-04-21T08:00:00+00:00",
                                "Build APIs with Python and FastAPI.",
                                analytics_json,
                                100000,
                                120000,
                                "CHF",
                                "YEAR",
                                "CHF 100000-120000 / year",
                            )
                            for vacancy_id, source, title in rows
                        ],
                    )
                    connection.commit()
                finally:
                    connection.close()

            _, analytics_paths, public_paths = rebuild_runtime_statistics(
                dataset_paths=[database_a, database_b],
                analytics_output_dir=analytics_output,
                public_stats_dir=public_data,
                public_csv_dir=public_csv,
                top_skills_limit=5,
                top_skill_pairs_limit=5,
            )

            overview = json.loads((public_data / "overview.json").read_text(encoding="utf-8"))

        self.assertTrue(analytics_paths)
        self.assertTrue(public_paths)
        self.assertEqual(2, overview["metrics"]["total_vacancies"])


if __name__ == "__main__":
    unittest.main()

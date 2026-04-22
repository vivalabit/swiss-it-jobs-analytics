from __future__ import annotations

import unittest
import sqlite3
import tempfile
from pathlib import Path

from swiss_jobs.providers.linked_in.client import (
    LinkedInHttpClient,
    _build_browser_proxy,
    _normalize_proxy_url,
)
from swiss_jobs.core.models import ClientConfig
from swiss_jobs.providers.linked_in.service import build_linkedin_queries, migrate_legacy_linkedin_ids


def parse_linkedin_test_vacancy():  # noqa: ANN201
    from swiss_jobs.core.models import VacancyFull

    return VacancyFull(
        id="linkedin:4211112222",
        title="Software Engineer",
        url="https://www.linkedin.com/jobs/view/4211112222/",
        raw={
            "linkedinJobId": "4211112222",
            "search_params": {
                "distance": "25.0",
                "geoId": "106693272",
                "keywords": "software engineer",
                "origin": "JOBS_HOME_KEYWORD_HISTORY",
            },
        },
    )


class LinkedInClientTests(unittest.TestCase):
    def test_client_builds_safe_default_search_params(self) -> None:
        client = LinkedInHttpClient()
        params = client._build_query_params(  # noqa: SLF001
            mode="search",
            term="software engineer",
            location="Zurich, Switzerland",
            page=2,
        )

        self.assertEqual("software engineer", params["keywords"])
        self.assertNotIn("location", params)
        self.assertEqual("106693272", params["geoId"])
        self.assertEqual("25.0", params["distance"])
        self.assertEqual("25", params["start"])
        self.assertEqual("JOBS_HOME_KEYWORD_HISTORY", params["origin"])

    def test_client_builds_current_job_detail_panel_url(self) -> None:
        client = LinkedInHttpClient()
        vacancy = parse_linkedin_test_vacancy()

        detail_url = client._build_detail_panel_url(vacancy)  # noqa: SLF001

        self.assertIn("currentJobId=4211112222", detail_url)
        self.assertIn("geoId=106693272", detail_url)
        self.assertIn("keywords=software+engineer", detail_url)

    def test_proxy_host_port_login_password_format_is_normalized(self) -> None:
        proxy_url = _normalize_proxy_url("gw.example.com:10002:user;city.zurich:secret")

        self.assertEqual("http://user%3Bcity.zurich:secret@gw.example.com:10002", proxy_url)

    def test_browser_proxy_keeps_credentials_separate(self) -> None:
        proxy = _build_browser_proxy("gw.example.com:10002:user;city.zurich:secret")

        self.assertEqual(
            {
                "server": "http://gw.example.com:10002",
                "username": "user;city.zurich",
                "password": "secret",
            },
            proxy,
        )

    def test_linkedin_queries_preserve_comma_in_location(self) -> None:
        config = ClientConfig.from_dict(
            {
                "mode": "search",
                "term": "software engineer",
                "location": "Zurich, Switzerland",
            },
            source="<test>",
        )

        queries = build_linkedin_queries(config)

        self.assertEqual(1, len(queries))
        self.assertEqual("Zurich, Switzerland", queries[0].location)

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

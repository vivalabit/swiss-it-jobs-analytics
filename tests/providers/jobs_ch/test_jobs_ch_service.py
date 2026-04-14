from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from swiss_jobs.core.formatter import build_brief
from swiss_jobs.core.models import ClientConfig, VacancyFull
from swiss_jobs.providers.jobs_ch.service import JobsChParserService


class FakeJobsChClient:
    def __init__(self, vacancies: list[VacancyFull]) -> None:
        self._vacancies = [vacancy.to_dict() for vacancy in vacancies]
        self.enrich_calls = 0

    def search(self, config: ClientConfig, queries):  # noqa: ANN001
        return [VacancyFull.from_dict(item) for item in self._vacancies], [], len(queries)

    def enrich_vacancies(self, vacancies, *, detail_limit, detail_workers, show_progress):  # noqa: ANN001
        self.enrich_calls += 1
        for vacancy in vacancies:
            vacancy.description_text = vacancy.description_text or "Detailed description"
        return len(vacancies), len(vacancies)

def make_config(payload: dict) -> ClientConfig:
    return ClientConfig.from_dict(payload, source="<test-config>", default_client_id="main-config")


class JobsChServiceTests(unittest.TestCase):
    def test_client_state_is_isolated(self) -> None:
        vacancy = VacancyFull(
            id="shared-1",
            title="Python Developer",
            company="Acme",
            place="Zurich",
            url="https://example.test/jobs/1",
        )
        fake_client = FakeJobsChClient([vacancy])

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_root = Path(tmpdir) / "runtime"
            base_config = {
                "mode": "search",
                "terms": ["python developer"],
                "locations": ["zurich"],
                "skip_detail_schema": True,
                "output_format": "brief",
            }
            config_a = make_config({"client_id": "client_a", "database_path": str(runtime_root / "client-a.sqlite"), **base_config})
            config_b = make_config({"client_id": "client_b", "database_path": str(runtime_root / "client-b.sqlite"), **base_config})

            service = JobsChParserService(http_client=fake_client, runtime_root=runtime_root)

            first_a = service.run(config_a)
            first_b = service.run(config_b)
            second_a = service.run(config_a)

            self.assertEqual(1, first_a.stats.new_jobs)
            self.assertEqual(1, first_b.stats.new_jobs)
            self.assertEqual(0, second_a.stats.new_jobs)
            db_a = runtime_root / "client-a.sqlite"
            db_b = runtime_root / "client-b.sqlite"
            self.assertTrue(db_a.exists())
            self.assertTrue(db_b.exists())

            connection = sqlite3.connect(db_a)
            try:
                seen_rows = connection.execute(
                    "SELECT vacancy_id FROM client_seen_vacancies WHERE client_id = ?",
                    ("client_a",),
                ).fetchall()
            finally:
                connection.close()
            self.assertEqual([("shared-1",)], seen_rows)

    def test_same_vacancy_id_does_not_conflict_between_clients(self) -> None:
        vacancy = VacancyFull(
            id="same-id",
            title="Data Analyst",
            company="Beta",
            place="Winterthur",
            url="https://example.test/jobs/2",
        )
        fake_client = FakeJobsChClient([vacancy])

        with tempfile.TemporaryDirectory() as tmpdir:
            payload = {
                "database_path": str(Path(tmpdir) / "shared.sqlite"),
                "mode": "search",
                "terms": ["data analyst"],
                "locations": ["winterthur"],
                "skip_detail_schema": True,
            }
            config_a = make_config({"client_id": "client_a", **payload})
            config_b = make_config({"client_id": "client_b", **payload})

            service = JobsChParserService(http_client=fake_client, runtime_root=Path(tmpdir))

            result_a = service.run(config_a)
            result_b = service.run(config_b)

            self.assertEqual(["same-id"], [job.id for job in result_a.new_jobs_full])
            self.assertEqual(["same-id"], [job.id for job in result_b.new_jobs_full])

    def test_brief_is_built_from_full(self) -> None:
        vacancy = VacancyFull(
            id="vac-1",
            title="Backend Developer",
            company="Gamma",
            place="Zurich",
            publication_date="2026-03-24",
            url="https://example.test/jobs/3",
            description_text="Build APIs and services for analytics products.",
            keywords_matched=["backend developer", "junior"],
        )
        vacancy.role_match = True
        vacancy.seniority_match = True

        brief = build_brief(vacancy).to_dict()

        self.assertEqual("vac-1", brief["id"])
        self.assertEqual("Gamma", brief["company"])
        self.assertEqual("Zurich", brief["location"])
        self.assertIn("Build APIs", brief["summary"])
        self.assertNotIn("description_text", brief)

    def test_override_applies_to_single_run_only(self) -> None:
        vacancy = VacancyFull(
            id="vac-2",
            title="Business Analyst",
            company="Delta",
            place="Zurich",
            url="https://example.test/jobs/4",
        )
        fake_client = FakeJobsChClient([vacancy])

        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(
                {
                    "client_id": "client_a",
                    "database_path": str(Path(tmpdir) / "client-a.sqlite"),
                    "mode": "search",
                    "terms": ["business analyst"],
                    "locations": ["zurich"],
                    "output_format": "full",
                    "skip_detail_schema": True,
                },
            )

            service = JobsChParserService(http_client=fake_client, runtime_root=Path(tmpdir))
            brief_result = service.run(config.with_overrides({"output_format": "brief"}, source="<brief>"))
            full_result = service.run(config.with_overrides({"use_state": False}, source="<full>"))

            self.assertIn("summary", brief_result.output_jobs[0])
            self.assertIn("raw", full_result.output_jobs[0])

    def test_brief_does_not_require_detail_fetch(self) -> None:
        vacancy = VacancyFull(
            id="vac-3",
            title="Junior Python Developer",
            company="Omega",
            place="Zurich",
            url="https://example.test/jobs/5",
        )
        fake_client = FakeJobsChClient([vacancy])

        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(
                {
                    "client_id": "client_a",
                    "database_path": str(Path(tmpdir) / "client-a.sqlite"),
                    "mode": "search",
                    "terms": ["python developer"],
                    "locations": ["zurich"],
                    "output_format": "brief",
                    "skip_detail_schema": True,
                },
            )

            service = JobsChParserService(http_client=fake_client, runtime_root=Path(tmpdir))
            result = service.run(config)

            self.assertEqual(0, fake_client.enrich_calls)
            self.assertEqual("brief", result.effective_config.output_format)
            self.assertEqual(1, len(result.output_jobs))

    def test_full_output_contains_analytics(self) -> None:
        vacancy = VacancyFull(
            id="vac-4",
            title="DevOps Engineer",
            company="Ops",
            place="Zurich",
            description_text="Work with AWS, Kubernetes, Docker and Python.",
            url="https://example.test/jobs/6",
        )
        fake_client = FakeJobsChClient([vacancy])

        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(
                {
                    "client_id": "client_a",
                    "database_path": str(Path(tmpdir) / "client-a.sqlite"),
                    "mode": "search",
                    "terms": ["devops engineer"],
                    "locations": ["zurich"],
                    "output_format": "full",
                    "skip_detail_schema": True,
                },
            )

            service = JobsChParserService(http_client=fake_client, runtime_root=Path(tmpdir))
            result = service.run(config)

            analytics = result.output_jobs[0]["analytics"]
            self.assertIn("devops_cloud_platform", analytics["role_family_matches"])
            self.assertIn("aws", analytics["cloud_platforms"])
            self.assertIn("python", analytics["programming_languages"])
            self.assertTrue(result.database_path)

    def test_role_filter_is_applied_after_detail_enrichment(self) -> None:
        vacancy = VacancyFull(
            id="vac-5",
            title="Engineer",
            company="Acme",
            place="Zurich",
            url="https://example.test/jobs/7",
        )

        class EnrichingClient(FakeJobsChClient):
            def enrich_vacancies(self, vacancies, *, detail_limit, detail_workers, show_progress):  # noqa: ANN001
                self.enrich_calls += 1
                for item in vacancies:
                    item.description_text = "This role is for a platform engineer working on cloud systems."
                return len(vacancies), len(vacancies)

        fake_client = EnrichingClient([vacancy])

        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(
                {
                    "client_id": "client_a",
                    "database_path": str(Path(tmpdir) / "client-a.sqlite"),
                    "mode": "search",
                    "terms": ["engineer"],
                    "locations": ["zurich"],
                    "role_keywords": ["platform engineer"],
                    "output_format": "brief",
                },
            )

            service = JobsChParserService(http_client=fake_client, runtime_root=Path(tmpdir))
            result = service.run(config)

            self.assertEqual(1, fake_client.enrich_calls)
            self.assertEqual(1, len(result.output_jobs))
            self.assertEqual(["platform engineer"], result.output_jobs[0]["keywords_matched"])


if __name__ == "__main__":
    unittest.main()

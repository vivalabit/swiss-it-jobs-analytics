from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_analytics.io import load_dataset
from swiss_jobs.cli.analyze_vacancies_llm import build_parser, load_dotenv
from swiss_jobs.core.database import JobsDatabase
from swiss_jobs.core.llm_analysis import (
    OpenAIVacancyAnalyzer,
    RequestsOpenAIResponsesTransport,
)
from swiss_jobs.core.models import ClientConfig, ClientRunResult, ParserStats, VacancyFull


class FakeOpenAITransport:
    def __init__(self, response_payloads: list[dict]) -> None:
        self._payloads = list(response_payloads)
        self.calls: list[dict] = []

    def create_response(self, payload, *, api_key: str, timeout_seconds: float):  # noqa: ANN001
        self.calls.append(
            {
                "payload": payload,
                "api_key": api_key,
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self._payloads:
            raise AssertionError("No fake OpenAI responses left")
        item = self._payloads.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _persist_sample_vacancy(
    database_path: Path,
    *,
    vacancy_id: str = "swissdevjobs:1",
    title: str = "Platform Engineer",
    place: str = "Zurich",
) -> None:
    vacancy = VacancyFull(
        id=vacancy_id,
        title=title,
        company="Acme",
        place=place,
        publication_date="2026-04-20T10:00:00+02:00",
        url="https://swissdevjobs.ch/jobs/platform-engineer",
        source="swissdevjobs.ch",
        description_text=(
            "Senior Python engineer for internal data platform. "
            "Hybrid setup with two home office days, office in Bern."
        ),
        raw={"employmentType": "Full-time"},
    )
    vacancy.extra["analytics"] = {
        "role_family_primary": "devops_cloud_platform",
        "role_family_matches": ["devops_cloud_platform"],
        "seniority_labels": ["mid"],
        "remote_mode": "onsite",
        "job_location": {"locality": "Zurich"},
    }

    config = ClientConfig.from_dict(
        {
            "client_id": "test",
            "name": "test",
            "mode": "new",
            "database_path": str(database_path),
            "output_format": "brief",
        },
        source="<test>",
        default_client_id="test",
    )
    result = ClientRunResult(
        run_id="run-1",
        client_id="test",
        timestamp="2026-04-24T10:00:00+00:00",
        effective_config=config,
        stats=ParserStats(total_fetched=1, after_text_filters=1, after_role_filters=1, new_jobs=1),
        new_jobs_full=[vacancy],
        all_jobs_full=[vacancy],
        output_jobs=[vacancy.to_dict()],
    )
    JobsDatabase(database_path).persist_result(config, result)


class LlmVacancyAnalysisTests(unittest.TestCase):
    def test_cli_loads_openai_api_key_from_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_path = Path(tmpdir) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "# local secrets",
                        "OPENAI_API_KEY='dotenv-key'",
                        "IGNORED_WITH_COMMENT=value # comment",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                load_dotenv(dotenv_path)
                analyzer = OpenAIVacancyAnalyzer()
                self.assertEqual("value", os.environ["IGNORED_WITH_COMMENT"])

        self.assertEqual("dotenv-key", analyzer.api_key)

    def test_cli_dotenv_does_not_override_existing_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_path = Path(tmpdir) / ".env"
            dotenv_path.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")

            with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}, clear=True):
                load_dotenv(dotenv_path)
                analyzer = OpenAIVacancyAnalyzer()

        self.assertEqual("env-key", analyzer.api_key)

    def test_analyzer_strips_api_key_whitespace(self) -> None:
        analyzer = OpenAIVacancyAnalyzer(api_key=" test-key\n")
        self.assertEqual("test-key", analyzer.api_key)

    def test_analyzer_emits_progress_logs(self) -> None:
        fake_transport = FakeOpenAITransport(
            [
                {
                    "output_text": json.dumps(
                        {
                            "normalized_title": "Senior Platform Engineer",
                            "role_family_primary": "devops_cloud_platform",
                            "role_family_matches": ["devops_cloud_platform"],
                            "seniority_labels": ["senior"],
                            "remote_mode": "hybrid",
                            "job_location": {
                                "locality": "Bern",
                                "region": "BE",
                                "country": "CH",
                            },
                            "employment_types": ["full-time"],
                            "programming_languages": ["python"],
                            "frameworks_libraries": [],
                            "cloud_platforms": [],
                            "data_platforms": [],
                            "databases": [],
                            "platforms": [],
                            "tools": [],
                            "vendors": [],
                            "protocols_standards": [],
                            "methodologies": [],
                            "spoken_languages": ["english"],
                            "confidence": "high",
                            "confidence_reasons": ["explicit_senior_scope"],
                        }
                    ),
                    "usage": {"input_tokens": 1000, "output_tokens": 200},
                }
            ]
        )
        logs: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "swissdevjobs.sqlite"
            _persist_sample_vacancy(database_path)
            analyzer = OpenAIVacancyAnalyzer(
                api_key="test-key",
                transport=fake_transport,
                progress_logger=logs.append,
            )
            analyzer.analyze_database(str(database_path), limit=1, dry_run=True)

        self.assertTrue(any("Starting OpenAI vacancy analysis" in log for log in logs))
        self.assertTrue(any("[1/1] analyzing" in log for log in logs))
        self.assertTrue(any("[1/1] analyzed" in log for log in logs))
        self.assertTrue(any("Completed OpenAI vacancy analysis" in log for log in logs))

    def test_analyzer_can_disable_progress_logs(self) -> None:
        analyzer = OpenAIVacancyAnalyzer(api_key="test-key", progress_logger=None)
        self.assertIsNone(analyzer.progress_logger)

    def test_requests_transport_retries_transient_520(self) -> None:
        class FakeResponse:
            def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
                self.status_code = status_code
                self._payload = payload or {}
                self.text = text

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    import requests

                    raise requests.HTTPError(f"status={self.status_code}", response=self)

            def json(self) -> dict:
                return self._payload

        responses = [
            FakeResponse(520, text="temporary edge failure"),
            FakeResponse(200, payload={"output_text": "{}", "usage": {"input_tokens": 1, "output_tokens": 1}}),
        ]

        transport = RequestsOpenAIResponsesTransport(max_attempts=2, initial_backoff_seconds=0.0)
        with patch("swiss_jobs.core.llm_analysis.requests.post", side_effect=responses) as mocked_post:
            result = transport.create_response(
                {"model": "gpt-5-nano"},
                api_key="test-key",
                timeout_seconds=1.0,
            )

        self.assertEqual("{}", result["output_text"])
        self.assertEqual(2, mocked_post.call_count)

    def test_analyzer_saves_llm_analysis_and_market_loader_uses_it(self) -> None:
        fake_transport = FakeOpenAITransport(
            [
                {
                    "output_text": json.dumps(
                        {
                            "normalized_title": "Senior Platform Engineer",
                            "role_family_primary": "devops_cloud_platform",
                            "role_family_matches": ["devops_cloud_platform"],
                            "seniority_labels": ["senior"],
                            "remote_mode": "hybrid",
                            "job_location": {
                                "locality": "Bern",
                                "region": "BE",
                                "country": "CH",
                            },
                            "employment_types": ["full-time"],
                            "programming_languages": ["python"],
                            "frameworks_libraries": [],
                            "cloud_platforms": ["aws"],
                            "data_platforms": ["airflow"],
                            "databases": ["postgresql"],
                            "platforms": [],
                            "tools": ["terraform"],
                            "vendors": [],
                            "protocols_standards": [],
                            "methodologies": ["devops"],
                            "spoken_languages": ["english"],
                            "confidence": "high",
                            "confidence_reasons": ["explicit_senior_scope"],
                        }
                    ),
                    "usage": {"input_tokens": 1500, "output_tokens": 250},
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "swissdevjobs.sqlite"
            _persist_sample_vacancy(database_path)

            analyzer = OpenAIVacancyAnalyzer(
                api_key="test-key",
                transport=fake_transport,
            )
            stats, previews = analyzer.analyze_database(
                str(database_path),
                source="swissdevjobs.ch",
                limit=1,
                dry_run=False,
            )

            self.assertEqual(1, stats.processed)
            self.assertEqual(1, stats.updated)
            self.assertEqual(1, len(previews))

            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute(
                    """
                    SELECT llm_analysis_json, llm_model, llm_analyzed_at
                    FROM vacancies
                    WHERE vacancy_id = 'swissdevjobs:1'
                    """
                ).fetchone()
                self.assertIsNotNone(row)
                llm_analysis = json.loads(row["llm_analysis_json"])
                self.assertEqual(["senior"], llm_analysis["seniority_labels"])
                self.assertEqual("gpt-5-nano", row["llm_model"])
                self.assertTrue(row["llm_analyzed_at"])

                terms = {
                    (term_type, term_value)
                    for term_type, term_value in connection.execute(
                        """
                        SELECT term_type, term_value
                        FROM vacancy_terms
                        WHERE vacancy_id = 'swissdevjobs:1'
                        """
                    ).fetchall()
                }
            finally:
                connection.close()

            self.assertIn(("seniority", "senior"), terms)
            self.assertIn(("programming_language", "python"), terms)

            dataset = load_dataset(database_path)
            self.assertEqual(1, len(dataset))
            self.assertEqual("senior", dataset.iloc[0]["seniority"])
            self.assertEqual("hybrid", dataset.iloc[0]["work_mode"])
            self.assertEqual("Bern", dataset.iloc[0]["city"])
            self.assertEqual("BE", dataset.iloc[0]["canton"])

    def test_followup_crawl_preserves_llm_enriched_terms(self) -> None:
        llm_analysis = {
            "role_family_primary": "software_engineering",
            "role_family_matches": ["software_engineering"],
            "seniority_labels": ["senior"],
            "programming_languages": ["python"],
            "frameworks_libraries": [],
            "cloud_platforms": [],
            "data_platforms": [],
            "databases": [],
            "platforms": [],
            "tools": ["terraform"],
            "methodologies": ["devops"],
            "remote_mode": "hybrid",
            "job_location": {"locality": "Bern", "region": "BE"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "swissdevjobs.sqlite"
            _persist_sample_vacancy(database_path)
            database = JobsDatabase(database_path)
            database.save_llm_analysis(
                "swissdevjobs:1",
                llm_analysis=llm_analysis,
                model="gpt-5-nano",
                analyzed_at="2026-04-24T12:00:00+00:00",
            )

            vacancy = VacancyFull(
                id="swissdevjobs:1",
                title="Platform Engineer",
                company="Acme",
                place="Zurich",
                publication_date="2026-04-20T10:00:00+02:00",
                url="https://swissdevjobs.ch/jobs/platform-engineer",
                source="swissdevjobs.ch",
                description_text="Rule based crawl without LLM-enriched Python terms.",
                raw={"employmentType": "Full-time"},
            )
            vacancy.extra["analytics"] = {
                "role_family_primary": "devops_cloud_platform",
                "role_family_matches": ["devops_cloud_platform"],
                "seniority_labels": ["mid"],
                "remote_mode": "onsite",
                "job_location": {"locality": "Zurich"},
            }
            config = ClientConfig.from_dict(
                {
                    "client_id": "test",
                    "name": "test",
                    "mode": "new",
                    "database_path": str(database_path),
                    "output_format": "brief",
                },
                source="<test>",
                default_client_id="test",
            )
            result = ClientRunResult(
                run_id="run-2",
                client_id="test",
                timestamp="2026-04-25T10:00:00+00:00",
                effective_config=config,
                stats=ParserStats(total_fetched=1, after_text_filters=1, after_role_filters=1),
                new_jobs_full=[],
                all_jobs_full=[vacancy],
                output_jobs=[vacancy.to_dict()],
            )

            database.persist_result(config, result)

            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute(
                    """
                    SELECT llm_analysis_json
                    FROM vacancies
                    WHERE vacancy_id = 'swissdevjobs:1'
                    """
                ).fetchone()
                terms = {
                    (term_type, term_value)
                    for term_type, term_value in connection.execute(
                        """
                        SELECT term_type, term_value
                        FROM vacancy_terms
                        WHERE vacancy_id = 'swissdevjobs:1'
                        """
                    ).fetchall()
                }
            finally:
                connection.close()

            self.assertIsNotNone(row)
            self.assertEqual(
                ["python"],
                json.loads(row["llm_analysis_json"])["programming_languages"],
            )
            self.assertIn(("seniority", "senior"), terms)
            self.assertIn(("programming_language", "python"), terms)
            self.assertIn(("tool", "terraform"), terms)
            self.assertNotIn(("seniority", "mid"), terms)

    def test_estimate_cost_works_for_small_swissdevjobs_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "swissdevjobs.sqlite"
            _persist_sample_vacancy(database_path)

            analyzer = OpenAIVacancyAnalyzer(api_key="test-key")
            estimate = analyzer.estimate_cost(
                str(database_path),
                source="swissdevjobs.ch",
                limit=1,
            )

            self.assertEqual("gpt-5-nano", estimate.model)
            self.assertEqual(1, estimate.vacancy_count)
            self.assertGreater(estimate.estimated_input_tokens, 0)
            self.assertGreater(estimate.estimated_output_tokens, 0)
            self.assertGreater(estimate.estimated_total_cost_usd, 0.0)

    def test_llm_vacancy_selection_filters_by_first_seen_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "swissdevjobs.sqlite"
            _persist_sample_vacancy(database_path, vacancy_id="swissdevjobs:1", title="Old vacancy")
            _persist_sample_vacancy(database_path, vacancy_id="swissdevjobs:2", title="Fresh vacancy")

            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    "UPDATE vacancies SET first_seen_at = ? WHERE vacancy_id = ?",
                    ("2026-04-15T08:00:00+00:00", "swissdevjobs:1"),
                )
                connection.execute(
                    "UPDATE vacancies SET first_seen_at = ? WHERE vacancy_id = ?",
                    ("2026-05-10T08:00:00+00:00", "swissdevjobs:2"),
                )
                connection.commit()
            finally:
                connection.close()

            records = JobsDatabase(database_path).fetch_vacancies_for_llm(
                first_seen_from="2026-05-01",
                first_seen_to="2026-05-31",
            )
            estimate = OpenAIVacancyAnalyzer(api_key="test-key").estimate_cost(
                str(database_path),
                first_seen_from="2026-05-01",
                first_seen_to="2026-05-31",
            )

        self.assertEqual(["swissdevjobs:2"], [record.vacancy.id for record in records])
        self.assertEqual(1, estimate.vacancy_count)

    def test_cli_accepts_first_seen_date_filters(self) -> None:
        args = build_parser().parse_args(
            [
                "--first-seen-from",
                "01.05.2026",
                "--first-seen-to",
                "2026-05-31",
            ]
        )

        self.assertEqual("2026-05-01", args.first_seen_from)
        self.assertEqual("2026-05-31", args.first_seen_to)

    def test_analyzer_continues_after_single_vacancy_failure(self) -> None:
        fake_transport = FakeOpenAITransport(
            [
                RuntimeError("temporary openai issue"),
                {
                    "output_text": json.dumps(
                        {
                            "normalized_title": "Senior Platform Engineer",
                            "role_family_primary": "devops_cloud_platform",
                            "role_family_matches": ["devops_cloud_platform"],
                            "seniority_labels": ["senior"],
                            "remote_mode": "hybrid",
                            "job_location": {
                                "locality": "Bern",
                                "region": "BE",
                                "country": "CH",
                            },
                            "employment_types": ["full-time"],
                            "programming_languages": ["python"],
                            "frameworks_libraries": [],
                            "cloud_platforms": [],
                            "data_platforms": [],
                            "databases": [],
                            "platforms": [],
                            "tools": [],
                            "vendors": [],
                            "protocols_standards": [],
                            "methodologies": [],
                            "spoken_languages": ["english"],
                            "confidence": "high",
                            "confidence_reasons": ["explicit_senior_scope"],
                        }
                    ),
                    "usage": {"input_tokens": 1000, "output_tokens": 200},
                },
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "swissdevjobs.sqlite"
            _persist_sample_vacancy(database_path, vacancy_id="swissdevjobs:1", title="First vacancy")
            _persist_sample_vacancy(database_path, vacancy_id="swissdevjobs:2", title="Second vacancy")

            analyzer = OpenAIVacancyAnalyzer(api_key="test-key", transport=fake_transport)
            stats, previews = analyzer.analyze_database(
                str(database_path),
                limit=10,
                dry_run=False,
            )

            self.assertEqual(1, stats.processed)
            self.assertEqual(1, stats.updated)
            self.assertEqual(1, stats.failed)
            self.assertTrue(any("failures" in item for item in previews))

            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    """
                    SELECT vacancy_id, llm_analysis_json
                    FROM vacancies
                    ORDER BY vacancy_id
                    """
                ).fetchall()
            finally:
                connection.close()

            self.assertIsNone(rows[0]["llm_analysis_json"])
            self.assertTrue(rows[1]["llm_analysis_json"])


if __name__ == "__main__":
    unittest.main()

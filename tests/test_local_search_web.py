from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from swiss_jobs.cli import local_search_web
from swiss_jobs.cli.local_search_web import (
    PROJECT_ROOT,
    SOURCE_DATABASE_PATHS,
    _analysis_cli_args,
    _analysis_command,
    _parser_cli_args,
    _parser_command,
    _public_stats_command_plan,
    _public_stats_options,
    load_facets,
    search_local_databases,
)
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
    publication_date: str = "2026-05-28T08:00:00+02:00",
    salary_min: int | None = None,
    salary_max: int | None = None,
    keywords_matched: list[str] | None = None,
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
        publication_date=publication_date,
        initial_publication_date=publication_date,
        is_new=True,
        url=f"https://example.com/{vacancy_id}",
        source="jobs.ch",
        description_text=f"{title} role with local database search.",
        keywords_matched=list(keywords_matched or []),
        raw=raw,
        extra={"analytics": analytics},
    )


class LocalSearchWebTests(unittest.TestCase):
    def test_parser_command_matches_ui_payload_order(self) -> None:
        args = _parser_cli_args(
            {
                "mode": "search",
                "canton": "ZH",
                "term": "python",
                "location": "Zürich",
                "max_pages": "3",
                "detail_limit": "25",
            }
        )

        self.assertEqual(
            [
                local_search_web.sys.executable,
                "-m",
                "swiss_jobs.cli.parse",
                "--source",
                "jobs_ch",
                "--mode",
                "search",
                "--canton",
                "ZH",
                "--term",
                "python",
                "--location",
                "Zürich",
                "--max-pages",
                "3",
                "--detail-limit",
                "25",
            ],
            _parser_command("jobs_ch", args),
        )

    def test_analysis_cli_args_include_first_seen_date_filters(self) -> None:
        args = _analysis_cli_args(
            {
                "model": "gpt-5-mini",
                "scope": "all selected vacancies",
                "first_seen_from": "01.05.2026",
                "first_seen_to": "2026-05-31",
                "limit": "25",
            }
        )

        self.assertEqual(
            [
                "--model",
                "gpt-5-mini",
                "--first-seen-from",
                "2026-05-01",
                "--first-seen-to",
                "2026-05-31",
                "--include-analyzed",
                "--limit",
                "25",
            ],
            args,
        )

    def test_analysis_command_matches_ui_payload_order(self) -> None:
        args = _analysis_cli_args(
            {
                "model": "gpt-5-mini",
                "scope": "all selected vacancies",
                "first_seen_from": "01.05.2026",
                "first_seen_to": "2026-05-31",
                "limit": "25",
            }
        )

        self.assertEqual(
            [
                local_search_web.sys.executable,
                "-m",
                "swiss_jobs.cli.analyze_vacancies_llm",
                "--source",
                "jobup_ch",
                "--model",
                "gpt-5-mini",
                "--first-seen-from",
                "2026-05-01",
                "--first-seen-to",
                "2026-05-31",
                "--include-analyzed",
                "--limit",
                "25",
            ],
            _analysis_command("jobup_ch", args),
        )

    def test_public_stats_options_include_snapshot_salary_and_site_fields(self) -> None:
        options = _public_stats_options(
            {
                "output_dir": "public_stats_custom",
                "site_dir": "site/custom-public",
                "snapshot_date": "22.04.2026",
                "salary_group_minimum": "5",
                "sync_site": False,
            }
        )

        self.assertEqual("public_stats_custom", options["output_dir"])
        self.assertEqual("site/custom-public", options["site_dir"])
        self.assertEqual("2026-04-22", options["snapshot_date"])
        self.assertEqual("5", options["salary_group_minimum"])
        self.assertFalse(options["sync_site"])

    def test_public_stats_command_plan_matches_ui_payload_order(self) -> None:
        sources, commands = _public_stats_command_plan(
            {
                "sources": ["jobup_ch"],
                "output_dir": "public_stats_custom",
                "site_dir": "site/custom-public",
                "snapshot_date": "22.04.2026",
                "salary_group_minimum": "5",
                "sync_site": True,
            }
        )

        output_root = PROJECT_ROOT / "public_stats_custom"
        analytics_dir = PROJECT_ROOT / "analytics_output"

        self.assertEqual(["jobup_ch"], sources)
        self.assertEqual(
            [
                (
                    "analytics",
                    [
                        local_search_web.sys.executable,
                        "scripts/export_analytics.py",
                        str(SOURCE_DATABASE_PATHS["jobup_ch"]),
                        "--output-dir",
                        str(analytics_dir),
                        "--salary-group-minimum",
                        "5",
                    ],
                ),
                (
                    "snapshot",
                    [
                        local_search_web.sys.executable,
                        "scripts/build_public_stats.py",
                        "--csv-dir",
                        str(analytics_dir),
                        "--output-dir",
                        str(output_root / "data"),
                        "--copy-csv-dir",
                        str(output_root / "csv"),
                        "--snapshot-date",
                        "2026-04-22",
                    ],
                ),
                (
                    "site-sync",
                    [
                        "node",
                        "site/scripts/sync-public-data.mjs",
                        "--source-public-dir",
                        str(output_root),
                        "--target-public-dir",
                        str(PROJECT_ROOT / "site" / "custom-public"),
                    ],
                ),
            ],
            commands,
        )

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
            result = payload["results"][0]
            self.assertEqual("Python Backend Engineer role with local database search.", result["description_text"])
            self.assertEqual("https://example.com/vacancy-1", result["url"])
            self.assertEqual("software_engineering", result["analytics"]["role_family_primary"])
            self.assertEqual("CHF", result["raw"]["salary"]["currency"])
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

    def test_search_local_databases_paginates_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancies = [
                make_vacancy(
                    f"vacancy-{index}",
                    title=f"Python Engineer {index}",
                    company="Acme",
                    place="Zurich",
                    analytics={
                        "role_family_primary": "software_engineering",
                        "programming_languages": ["python"],
                    },
                )
                for index in range(1, 4)
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, vacancies))

            payload = search_local_databases(
                [database_path],
                {
                    "q": ["python"],
                    "page": ["2"],
                    "per_page": ["1"],
                },
            )

            self.assertEqual(3, payload["total"])
            self.assertEqual(2, payload["page"])
            self.assertEqual(1, payload["per_page"])
            self.assertEqual(3, payload["total_pages"])
            self.assertEqual(1, len(payload["results"]))

    def test_search_local_databases_filters_by_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancies = [
                make_vacancy(
                    "vacancy-1",
                    title="Platform Engineer",
                    company="Acme",
                    place="Zurich",
                    keywords_matched=["event-driven"],
                    analytics={
                        "role_family_primary": "software_engineering",
                        "programming_languages": ["python"],
                    },
                ),
                make_vacancy(
                    "vacancy-2",
                    title="Platform Engineer",
                    company="Beta",
                    place="Bern",
                    keywords_matched=["linux"],
                    analytics={
                        "role_family_primary": "devops_cloud_platform",
                        "programming_languages": ["go"],
                    },
                ),
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, vacancies))

            payload = search_local_databases(
                [database_path],
                {
                    "keyword": ["event-driven"],
                    "limit": ["50"],
                },
            )

            self.assertEqual(["vacancy-1"], [item["id"] for item in payload["results"]])
            self.assertEqual(["event-driven"], payload["results"][0]["matched_keywords"])

    def test_search_local_databases_uses_effective_seniority_for_lead_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancies = [
                make_vacancy(
                    "vacancy-1",
                    title="Lead Fullstack Software Developer Java / Software Architect",
                    company="Yellowshark",
                    place="Bern oder Zürich",
                    analytics={
                        "role_family_primary": "software_engineering",
                        "seniority_labels": ["junior", "senior"],
                        "programming_languages": ["java"],
                    },
                ),
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, vacancies))

            senior_payload = search_local_databases([database_path], {"seniority": ["senior"]})
            junior_payload = search_local_databases([database_path], {"seniority": ["junior"]})

            self.assertEqual(["vacancy-1"], [item["id"] for item in senior_payload["results"]])
            self.assertEqual("senior", senior_payload["results"][0]["seniority"])
            self.assertEqual("junior, senior", senior_payload["results"][0]["detected_seniority"])
            self.assertEqual([], junior_payload["results"])

    def test_search_local_databases_filters_by_published_date_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancies = [
                make_vacancy(
                    "vacancy-1",
                    title="Python Engineer",
                    company="Acme",
                    place="Zurich",
                    publication_date="2026-05-28T08:00:00+02:00",
                    analytics={
                        "role_family_primary": "software_engineering",
                        "programming_languages": ["python"],
                    },
                ),
                make_vacancy(
                    "vacancy-2",
                    title="Python Engineer",
                    company="Beta",
                    place="Bern",
                    publication_date="2026-04-10T08:00:00+02:00",
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
                    "date_field": ["published"],
                    "date_from": ["01.05.2026"],
                    "date_to": ["31.05.2026"],
                    "limit": ["50"],
                },
            )

            self.assertEqual(["vacancy-1"], [item["id"] for item in payload["results"]])

    def test_search_local_databases_rejects_invalid_date_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "date_from must use YYYY-MM-DD or dd.mm.yyyy format"):
            search_local_databases([], {"date_from": ["2026/05/01"]})

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

    def test_persist_result_normalizes_location_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancies = [
                make_vacancy(
                    "vacancy-1",
                    title="Python Engineer",
                    company="Acme",
                    place="Zurich Switzerland",
                    analytics={"programming_languages": ["python"]},
                ),
                make_vacancy(
                    "vacancy-2",
                    title="Data Engineer",
                    company="Beta",
                    place="Berne",
                    analytics={"programming_languages": ["python"]},
                ),
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, vacancies))

            with closing(sqlite3.connect(database_path)) as connection:
                rows = connection.execute(
                    "SELECT vacancy_id, place FROM vacancies ORDER BY vacancy_id"
                ).fetchall()

            self.assertEqual(
                [("vacancy-1", "Zürich"), ("vacancy-2", "Bern")],
                rows,
            )

    def test_load_facets_collapses_legacy_location_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancies = [
                make_vacancy(
                    "vacancy-1",
                    title="Python Engineer",
                    company="Acme",
                    place="Zurich",
                    analytics={"programming_languages": ["python"]},
                ),
                make_vacancy(
                    "vacancy-2",
                    title="Data Engineer",
                    company="Beta",
                    place="Geneva",
                    analytics={"programming_languages": ["python"]},
                ),
                make_vacancy(
                    "vacancy-3",
                    title="Platform Engineer",
                    company="Gamma",
                    place="Berne",
                    analytics={"programming_languages": ["go"]},
                ),
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, vacancies))
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("UPDATE vacancies SET place = ? WHERE vacancy_id = ?", ("Zurich", "vacancy-1"))
                connection.execute("UPDATE vacancies SET place = ? WHERE vacancy_id = ?", ("Geneva", "vacancy-2"))
                connection.execute("UPDATE vacancies SET place = ? WHERE vacancy_id = ?", ("Berne", "vacancy-3"))
                connection.commit()

            facets = load_facets([database_path])

            self.assertIn({"value": "Zürich", "count": 1}, facets["locations"])
            self.assertIn({"value": "Genève", "count": 1}, facets["locations"])
            self.assertIn({"value": "Bern", "count": 1}, facets["locations"])
            self.assertNotIn({"value": "Zurich", "count": 1}, facets["locations"])
            self.assertNotIn({"value": "Geneva", "count": 1}, facets["locations"])
            self.assertNotIn({"value": "Berne", "count": 1}, facets["locations"])

    def test_search_location_filter_matches_legacy_aliases_and_displays_canonical_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "jobs.sqlite"
            config = make_config(database_path)
            vacancies = [
                make_vacancy(
                    "vacancy-1",
                    title="Python Engineer",
                    company="Acme",
                    place="Zurich",
                    analytics={"programming_languages": ["python"]},
                ),
            ]
            JobsDatabase(database_path).persist_result(config, make_result(config, vacancies))
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute(
                    "UPDATE vacancies SET place = ? WHERE vacancy_id = ?",
                    ("Zurich, Switzerland", "vacancy-1"),
                )
                connection.commit()

            payload = search_local_databases([database_path], {"location": ["Zürich"], "limit": ["50"]})

            self.assertEqual(["vacancy-1"], [item["id"] for item in payload["results"]])
            self.assertEqual("Zürich", payload["results"][0]["location"])


if __name__ == "__main__":
    unittest.main()

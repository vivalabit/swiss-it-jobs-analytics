from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
import sqlite3

from market_analytics.io import (
    load_and_validate_dataset,
    load_and_validate_datasets,
    validate_and_standardize_dataset,
)
from market_analytics.analytics import exclude_staffing_agencies
from market_analytics.deduplication import (
    build_cross_source_dedup_report,
    deduplicate_cross_source_vacancies,
)
from market_analytics.reporting import build_analytics_outputs, save_analytics_outputs


class MarketAnalyticsTests(unittest.TestCase):
    def test_validate_and_standardize_dataset_resolves_aliases_and_skills(self) -> None:
        dataset = pd.DataFrame(
            {
                "company_name": ["Acme", "Beta", None],
                "role_family_primary": [
                    "data_ai",
                    "software_engineering",
                    "data_ai",
                ],
                "place": ["Zurich", "Bern", "Geneva"],
                "state": ["ZH", "BE", None],
                "seniority_level": ["senior", "mid", None],
                "remote_mode": ["hybrid", "remote", None],
                "salary_min": [100000, 90000, None],
                "salary_max": [130000, 110000, None],
                "salary_currency": ["chf", "CHF", None],
                "salary_unit": ["year", "YEAR", None],
                "detected_skills": [
                    '["python", "sql", "airflow"]',
                    ["python", "pandas"],
                    "sql | excel",
                ],
            }
        )

        standardized = validate_and_standardize_dataset(dataset)

        self.assertIn("company", standardized.columns)
        self.assertIn("skills_list", standardized.columns)
        self.assertEqual("CHF", standardized.loc[0, "salary_currency"])
        self.assertEqual("YEAR", standardized.loc[0, "salary_unit"])
        self.assertEqual(["python", "sql", "airflow"], standardized.loc[0, "skills_list"])
        self.assertEqual(["sql", "excel"], standardized.loc[2, "skills_list"])
        self.assertTrue(pd.isna(standardized.loc[2, "work_mode"]))

    def test_validate_and_standardize_dataset_normalizes_city_and_canton(self) -> None:
        dataset = pd.DataFrame(
            {
                "company": ["Acme", "Beta", "Gamma", "Delta", "Epsilon"],
                "role_category": [
                    "data_ai",
                    "data_ai",
                    "software_engineering",
                    "software_engineering",
                    "data_ai",
                ],
                "city": ["Zurich", "Zürich", "Ecublens VD", "3173 / Köniz", "1020 Renens"],
                "canton": [None, "zurich", None, None, None],
                "seniority": ["senior", "mid", "junior", "senior", "mid"],
                "work_mode": ["hybrid", "remote", "onsite", "hybrid", "onsite"],
                "skills": [["python"], ["sql"], ["java"], ["go"], ["rust"]],
            }
        )

        standardized = validate_and_standardize_dataset(dataset)

        self.assertEqual("Zürich", standardized.loc[0, "city"])
        self.assertEqual("Zürich", standardized.loc[1, "city"])
        self.assertEqual("Ecublens", standardized.loc[2, "city"])
        self.assertEqual("Köniz", standardized.loc[3, "city"])
        self.assertEqual("Renens", standardized.loc[4, "city"])
        self.assertEqual("ZH", standardized.loc[0, "canton"])
        self.assertEqual("ZH", standardized.loc[1, "canton"])
        self.assertEqual("VD", standardized.loc[2, "canton"])
        self.assertEqual("BE", standardized.loc[3, "canton"])
        self.assertEqual("VD", standardized.loc[4, "canton"])

    def test_build_analytics_outputs_creates_expected_tables(self) -> None:
        dataset = pd.DataFrame(
            {
                "company": ["Acme", "Acme", "Beta", "Rocken®"],
                "title": [
                    "Data Engineer",
                    "Python Developer",
                    "Java Developer",
                    "Go Developer",
                ],
                "description_text": [
                    "University degree in computer science is required.",
                    "Strong Python delivery experience with at least 3 years.",
                    "Bachelor or Master in engineering.",
                    "Agency vacancy with FH degree mentioned.",
                ],
                "publication_date": [
                    "2026-04-20T10:00:00+02:00",
                    "2026-04-14T10:00:00+02:00",
                    "2026-03-01T10:00:00+01:00",
                    "2026-04-21T10:00:00+02:00",
                ],
                "first_seen_at": [
                    "2026-04-20T08:00:00+00:00",
                    "2026-04-14T08:00:00+00:00",
                    "2026-03-01T08:00:00+00:00",
                    "2026-04-21T08:00:00+00:00",
                ],
                "last_seen_at": [
                    "2026-04-21T08:00:00+00:00",
                    "2026-04-20T08:00:00+00:00",
                    "2026-04-21T08:00:00+00:00",
                    "2026-04-21T08:00:00+00:00",
                ],
                "role_category": ["data_ai", "data_ai", "software_engineering", "data_ai"],
                "city": ["Zurich", "Bern", "Zurich", "Zurich"],
                "canton": ["ZH", "BE", "ZH", "ZH"],
                "seniority": ["senior", "mid", "junior", "mid"],
                "work_mode": ["hybrid", "remote", "onsite", "hybrid"],
                "salary_min": [100000, 90000, 120000, None],
                "salary_max": [130000, 110000, 140000, None],
                "salary_currency": ["CHF", "CHF", "CHF", None],
                "salary_unit": ["YEAR", "YEAR", "YEAR", None],
                "programming_languages": [
                    ["python", "sql"],
                    ["python"],
                    ["java"],
                    ["go"],
                ],
                "frameworks_libraries": [
                    ["airflow"],
                    ["pandas"],
                    ["spring"],
                    ["react"],
                ],
                "skills": [
                    ["python", "sql", "airflow"],
                    ["python", "pandas"],
                    ["java", "spring"],
                    ["go", "react"],
                ],
            }
        )
        standardized = validate_and_standardize_dataset(dataset)

        outputs = build_analytics_outputs(standardized, top_skills_limit=5, top_skill_pairs_limit=5)

        self.assertEqual(30, len(outputs))
        overview = outputs["overview_metrics"].set_index("metric")["value"].to_dict()
        self.assertEqual(3, overview["total_vacancies"])
        self.assertEqual(2, overview["total_companies"])
        self.assertEqual(1.5, overview["average_vacancies_per_company"])
        self.assertEqual("Acme", outputs["distribution_company"].iloc[0]["company"])
        self.assertEqual(2, outputs["distribution_company"].iloc[0]["vacancy_count"])
        education_summary = outputs["education_requirements_summary"].set_index("metric")[
            "value"
        ].to_dict()
        self.assertEqual(3, education_summary["total_vacancies"])
        self.assertEqual(2, education_summary["higher_education_vacancy_count"])
        self.assertEqual(0.6667, education_summary["higher_education_vacancy_share"])
        experience_summary = outputs["experience_requirements_summary"].set_index("metric")[
            "value"
        ].to_dict()
        self.assertEqual(3, experience_summary["seniority_known_count"])
        self.assertEqual(1, experience_summary["experience_years_mentioned_count"])
        self.assertEqual(3.0, experience_summary["average_min_experience_years"])
        experience_by_seniority = outputs["experience_by_seniority"].set_index("seniority")
        self.assertEqual(1, experience_by_seniority.loc["mid", "experience_years_count"])
        trend_summary = outputs["vacancy_trends_summary"].set_index("metric")["value"].to_dict()
        self.assertEqual(3, trend_summary["published_total"])
        self.assertEqual(1, trend_summary["closed_total"])
        self.assertEqual(2, trend_summary["published_30d"])
        self.assertEqual(1, trend_summary["published_previous_30d"])
        self.assertIn("vacancy_trends_daily", outputs)
        self.assertIn("vacancy_trends_weekly", outputs)
        self.assertIn("vacancy_trends_monthly", outputs)
        self.assertIn("vacancy_trends_segments_daily", outputs)
        self.assertIn("vacancy_trends_segments_weekly", outputs)
        self.assertEqual(
            {"BE", "ZH"},
            set(outputs["vacancy_trends_segments_daily"]["canton"]),
        )
        self.assertEqual(
            "python",
            outputs["top_skills_overall"].iloc[0]["skill"],
        )
        self.assertIn("top_skills_by_canton", outputs)
        self.assertEqual(
            "python",
            outputs["top_programming_languages"].iloc[0]["programming_language"],
        )
        self.assertIn(
            "spring",
            set(outputs["top_frameworks_libraries"]["framework_library"]),
        )
        salary_summary = outputs["salary_summary"].set_index("metric")["value"].to_dict()
        self.assertEqual(3, salary_summary["salary_count"])
        self.assertEqual(115000, salary_summary["average_salary"])
        self.assertEqual(
            "software_engineering",
            outputs["salary_by_role_category"].iloc[0]["role_category"],
        )
        self.assertEqual("junior", outputs["salary_by_seniority"].iloc[0]["seniority"])
        self.assertNotIn("Rocken®", set(outputs["distribution_company"]["company"]))
        self.assertIn("city_map_details", outputs)
        city_map_details = outputs["city_map_details"].set_index("city")
        self.assertEqual(2, city_map_details.loc["Zürich", "vacancy_count"])
        self.assertIn("software_engineering", city_map_details.loc["Zürich", "role_distribution_json"])

    def test_build_analytics_outputs_excludes_pre_2026_publications_from_public_stats(self) -> None:
        dataset = pd.DataFrame(
            {
                "company": ["Acme", "Legacy Co", "Unknown Date Co"],
                "title": ["Data Engineer", "Old Python Engineer", "Missing Date Analyst"],
                "description_text": [
                    "Python and SQL.",
                    "Kotlin and Java.",
                    "Excel and BI.",
                ],
                "publication_date": [
                    "2026-04-20T10:00:00+02:00",
                    "2025-12-31T23:30:00+00:00",
                    None,
                ],
                "first_seen_at": [
                    "2026-04-20T08:00:00+00:00",
                    "2025-12-31T08:00:00+00:00",
                    "2026-04-21T08:00:00+00:00",
                ],
                "last_seen_at": [
                    "2026-04-21T08:00:00+00:00",
                    "2026-01-01T08:00:00+00:00",
                    "2026-04-21T08:00:00+00:00",
                ],
                "role_category": ["data_ai", "software_engineering", "product_project_analysis"],
                "city": ["Zurich", "Bern", "Geneva"],
                "canton": ["ZH", "BE", "GE"],
                "seniority": ["senior", "mid", "mid"],
                "work_mode": ["hybrid", "onsite", "remote"],
                "skills": [["python", "sql"], ["kotlin", "java"], ["excel"]],
            }
        )

        standardized = validate_and_standardize_dataset(dataset)
        outputs = build_analytics_outputs(standardized, top_skills_limit=5, top_skill_pairs_limit=5)

        overview = outputs["overview_metrics"].set_index("metric")["value"].to_dict()
        self.assertEqual(1, overview["total_vacancies"])
        self.assertEqual(1, overview["total_companies"])
        self.assertEqual({"Acme"}, set(outputs["distribution_company"]["company"]))
        self.assertEqual(
            {"2026-04-20"},
            set(outputs["vacancy_trends_daily"]["date"]),
        )
        trend_summary = outputs["vacancy_trends_summary"].set_index("metric")["value"].to_dict()
        self.assertEqual(1, trend_summary["published_total"])
        self.assertEqual("2026-04-20", trend_summary["latest_publication_date"])

    def test_exclude_staffing_agencies_removes_normalized_agency_names(self) -> None:
        dataset = pd.DataFrame(
            {
                "company": [
                    "Acme AG",
                    "Rocken®",
                    "The Adecco Group",
                    "Approach People Recruitment SA",
                ],
                "role_category": ["software_engineering"] * 4,
                "city": ["Zürich"] * 4,
                "canton": ["ZH"] * 4,
                "seniority": ["mid"] * 4,
                "work_mode": ["hybrid"] * 4,
                "skills": [["python"]] * 4,
            }
        )

        filtered = exclude_staffing_agencies(validate_and_standardize_dataset(dataset))

        self.assertEqual(["Acme AG"], filtered["company"].tolist())

    def test_cross_source_deduplication_merges_same_vacancy(self) -> None:
        dataset = pd.DataFrame(
            {
                "vacancy_id": ["jobs-1", "linkedin-1"],
                "source": ["jobs.ch", "linkedin.com"],
                "company": ["Acme AG", "Acme"],
                "title": ["Senior Python Engineer", "Senior Python Engineer"],
                "description_text": [
                    "Build data platforms with Python, Airflow, and AWS for internal analytics.",
                    "Build data platforms with Python and AWS for internal analytics teams.",
                ],
                "publication_date": [
                    "2026-04-20T10:00:00+02:00",
                    "2026-04-22T09:00:00+02:00",
                ],
                "role_category": ["data_ai", "data_ai"],
                "city": ["Zürich", "Zurich"],
                "canton": ["ZH", "ZH"],
                "seniority": ["senior", "senior"],
                "work_mode": ["hybrid", "hybrid"],
                "skills": [["python", "airflow"], ["python", "aws"]],
                "programming_languages": [["python"], ["python"]],
                "frameworks_libraries": [["airflow"], ["pandas"]],
            }
        )

        standardized = validate_and_standardize_dataset(dataset)
        deduped = deduplicate_cross_source_vacancies(standardized)

        self.assertEqual(1, len(deduped))
        self.assertTrue(deduped.loc[0, "is_cross_source_duplicate"])
        self.assertEqual(2, deduped.loc[0, "duplicate_source_count"])
        self.assertEqual(["jobs.ch", "linkedin.com"], deduped.loc[0, "duplicate_sources"])
        self.assertEqual(
            {"python", "airflow", "aws"},
            set(deduped.loc[0, "skills_list"]),
        )
        self.assertEqual(
            {"airflow", "pandas"},
            set(deduped.loc[0, "frameworks_libraries_list"]),
        )

    def test_cross_source_deduplication_keeps_distinct_roles(self) -> None:
        dataset = pd.DataFrame(
            {
                "vacancy_id": ["jobs-1", "linkedin-1"],
                "source": ["jobs.ch", "linkedin.com"],
                "company": ["Acme AG", "Acme"],
                "title": ["Senior Python Engineer", "Senior Data Analyst"],
                "description_text": [
                    "Build backend services and data platforms with Python and AWS.",
                    "Analyze business metrics in SQL and build dashboards for finance.",
                ],
                "publication_date": [
                    "2026-04-20T10:00:00+02:00",
                    "2026-04-22T09:00:00+02:00",
                ],
                "role_category": ["software_engineering", "data_ai"],
                "city": ["Zürich", "Zurich"],
                "canton": ["ZH", "ZH"],
                "seniority": ["senior", "senior"],
                "work_mode": ["hybrid", "hybrid"],
                "skills": [["python", "aws"], ["sql", "tableau"]],
            }
        )

        standardized = validate_and_standardize_dataset(dataset)
        deduped = deduplicate_cross_source_vacancies(standardized)

        self.assertEqual(2, len(deduped))
        self.assertFalse(deduped["is_cross_source_duplicate"].any())

    def test_cross_source_dedup_report_lists_original_rows(self) -> None:
        dataset = pd.DataFrame(
            {
                "vacancy_id": ["jobs-1", "linkedin-1", "jobup-1"],
                "source": ["jobs.ch", "linkedin.com", "jobup.ch"],
                "company": ["Acme AG", "Acme", "Beta AG"],
                "title": [
                    "Senior Python Engineer",
                    "Senior Python Engineer",
                    "Platform Engineer",
                ],
                "description_text": [
                    "Build data platforms with Python and AWS.",
                    "Build data platforms with Python and AWS for analytics.",
                    "Operate Kubernetes clusters and CI pipelines.",
                ],
                "publication_date": [
                    "2026-04-20T10:00:00+02:00",
                    "2026-04-22T09:00:00+02:00",
                    "2026-04-22T09:00:00+02:00",
                ],
                "role_category": ["software_engineering", "software_engineering", "devops_cloud"],
                "city": ["Zürich", "Zurich", "Bern"],
                "canton": ["ZH", "ZH", "BE"],
                "seniority": ["senior", "senior", "mid"],
                "work_mode": ["hybrid", "hybrid", "hybrid"],
                "skills": [["python", "aws"], ["python", "aws"], ["kubernetes"]],
            }
        )

        standardized = validate_and_standardize_dataset(dataset)
        report = build_cross_source_dedup_report(standardized)

        self.assertEqual(2, len(report))
        self.assertEqual(1, report["duplicate_group_id"].nunique())
        self.assertEqual(1, int(report["is_canonical"].sum()))
        self.assertEqual({"jobs.ch", "linkedin.com"}, set(report["source"]))
        self.assertEqual(2, int(report["duplicate_vacancy_count"].max()))

    def test_load_and_save_outputs_round_trip_csv(self) -> None:
        dataset = pd.DataFrame(
            {
                "company": ["Acme"],
                "role_category": ["data_ai"],
                "city": ["Zurich"],
                "canton": ["ZH"],
                "seniority": ["senior"],
                "work_mode": ["hybrid"],
                "skills": ['["python", "sql"]'],
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dataset_path = temp_path / "dataset.csv"
            dataset.to_csv(dataset_path, index=False)

            loaded = load_and_validate_dataset(dataset_path)
            outputs = build_analytics_outputs(loaded)
            saved_files = save_analytics_outputs(outputs, temp_path / "results")

            self.assertTrue(saved_files)
            self.assertTrue((temp_path / "results" / "overview_metrics.csv").exists())

    def test_load_and_validate_dataset_from_sqlite(self) -> None:
        analytics_json = """
        {
          "role_family_primary": "data_ai",
          "seniority_labels": ["senior"],
          "experience_years": {"min": 5},
          "remote_mode": "hybrid",
          "job_location": {"locality": "Zurich", "region": "ZH"},
          "programming_languages": ["python", "sql"],
          "frameworks_libraries": ["airflow"],
          "cloud_platforms": ["aws"]
        }
        """.strip()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            database_path = temp_path / "jobs_ch.sqlite"

            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE vacancies (
                        vacancy_id TEXT PRIMARY KEY,
                        company TEXT,
                        place TEXT,
                        analytics_json TEXT,
                        salary_min INTEGER,
                        salary_max INTEGER,
                        salary_currency TEXT,
                        salary_unit TEXT,
                        salary_text TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO vacancies (
                        vacancy_id,
                        company,
                        place,
                        analytics_json,
                        salary_min,
                        salary_max,
                        salary_currency,
                        salary_unit,
                        salary_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "vacancy-1",
                        "Acme",
                        "Zurich",
                        analytics_json,
                        100000,
                        120000,
                        "CHF",
                        "YEAR",
                        "CHF 100000-120000 / year",
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            loaded = load_and_validate_dataset(database_path)

            self.assertEqual("Acme", loaded.loc[0, "company"])
            self.assertEqual("data_ai", loaded.loc[0, "role_category"])
            self.assertEqual("ZH", loaded.loc[0, "canton"])
            self.assertEqual(5, loaded.loc[0, "experience_years_min"])
            self.assertEqual(["python", "sql"], loaded.loc[0, "programming_languages_list"])
            self.assertEqual(["airflow"], loaded.loc[0, "frameworks_libraries_list"])
            self.assertEqual(["python", "sql", "airflow", "aws"], loaded.loc[0, "skills_list"])
            self.assertEqual(100000, loaded.loc[0, "salary_min"])
            self.assertEqual("CHF", loaded.loc[0, "salary_currency"])

    def test_load_and_validate_datasets_combines_multiple_sqlite_inputs(self) -> None:
        analytics_json_a = """
        {
          "role_family_primary": "data_ai",
          "seniority_labels": ["senior"],
          "remote_mode": "hybrid",
          "job_location": {"locality": "Zurich", "region": "ZH"},
          "programming_languages": ["python"]
        }
        """.strip()
        analytics_json_b = """
        {
          "role_family_primary": "software_engineering",
          "seniority_labels": ["mid"],
          "remote_mode": "onsite",
          "job_location": {"locality": "Bern", "region": "BE"},
          "programming_languages": ["java"]
        }
        """.strip()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            database_a = temp_path / "jobs_ch.sqlite"
            database_b = temp_path / "jobscout24_ch.sqlite"

            for database_path, source, vacancy_id, company, place, analytics_json in (
                (database_a, "jobs.ch", "vacancy-1", "Acme", "Zurich", analytics_json_a),
                (database_b, "jobscout24.ch", "vacancy-2", "Beta", "Bern", analytics_json_b),
            ):
                connection = sqlite3.connect(database_path)
                try:
                    connection.execute(
                        """
                        CREATE TABLE vacancies (
                            vacancy_id TEXT PRIMARY KEY,
                            source TEXT,
                            company TEXT,
                            place TEXT,
                            analytics_json TEXT
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO vacancies (vacancy_id, source, company, place, analytics_json)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (vacancy_id, source, company, place, analytics_json),
                    )
                    connection.commit()
                finally:
                    connection.close()

            loaded = load_and_validate_datasets([database_a, database_b])

            self.assertEqual(2, len(loaded))
            self.assertEqual({"Acme", "Beta"}, set(loaded["company"]))
            self.assertEqual({"ZH", "BE"}, set(loaded["canton"]))


if __name__ == "__main__":
    unittest.main()

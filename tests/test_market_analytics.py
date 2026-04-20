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
                "company": ["Acme", "Acme", "Beta"],
                "role_category": ["data_ai", "data_ai", "software_engineering"],
                "city": ["Zurich", "Bern", "Zurich"],
                "canton": ["ZH", "BE", "ZH"],
                "seniority": ["senior", "mid", "junior"],
                "work_mode": ["hybrid", "remote", "onsite"],
                "salary_min": [100000, 90000, 120000],
                "salary_max": [130000, 110000, 140000],
                "salary_currency": ["CHF", "CHF", "CHF"],
                "salary_unit": ["YEAR", "YEAR", "YEAR"],
                "programming_languages": [
                    ["python", "sql"],
                    ["python"],
                    ["java"],
                ],
                "frameworks_libraries": [
                    ["airflow"],
                    ["pandas"],
                    ["spring"],
                ],
                "skills": [
                    ["python", "sql", "airflow"],
                    ["python", "pandas"],
                    ["java", "spring"],
                ],
            }
        )
        standardized = validate_and_standardize_dataset(dataset)

        outputs = build_analytics_outputs(standardized, top_skills_limit=5, top_skill_pairs_limit=5)

        self.assertEqual(20, len(outputs))
        overview = outputs["overview_metrics"].set_index("metric")["value"].to_dict()
        self.assertEqual(3, overview["total_vacancies"])
        self.assertEqual(2, overview["total_companies"])
        self.assertEqual(1.5, overview["average_vacancies_per_company"])
        self.assertEqual("Acme", outputs["distribution_company"].iloc[0]["company"])
        self.assertEqual(2, outputs["distribution_company"].iloc[0]["vacancy_count"])
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

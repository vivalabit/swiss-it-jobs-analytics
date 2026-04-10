from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
import sqlite3

from market_analytics.io import load_and_validate_dataset, validate_and_standardize_dataset
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

        self.assertEqual(16, len(outputs))
        overview = outputs["overview_metrics"].set_index("metric")["value"].to_dict()
        self.assertEqual(3, overview["total_vacancies"])
        self.assertEqual(2, overview["total_companies"])
        self.assertEqual(1.5, overview["average_vacancies_per_company"])
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
                        analytics_json TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO vacancies (vacancy_id, company, place, analytics_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("vacancy-1", "Acme", "Zurich", analytics_json),
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


if __name__ == "__main__":
    unittest.main()

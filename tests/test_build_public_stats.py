from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd


def _load_build_public_stats_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "build_public_stats.py"
    spec = importlib.util.spec_from_file_location("build_public_stats", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load scripts/build_public_stats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_public_stats = _load_build_public_stats_module()


class BuildPublicStatsTests(unittest.TestCase):
    def test_build_public_snapshots_creates_expected_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_dir = temp_path / "analytics_output"
            output_dir = temp_path / "public_stats" / "data"
            copy_csv_dir = temp_path / "public_stats" / "csv"
            csv_dir.mkdir(parents=True)

            pd.DataFrame(
                [
                    {"metric": "total_vacancies", "value": 3},
                    {"metric": "total_companies", "value": 2},
                    {"metric": "average_vacancies_per_company", "value": 1.5},
                ]
            ).to_csv(csv_dir / "overview_metrics.csv", index=False)
            pd.DataFrame(
                [
                    {"metric": "total_vacancies", "value": 3},
                    {"metric": "higher_education_vacancy_count", "value": 2},
                    {"metric": "higher_education_vacancy_share", "value": 0.6667},
                    {"metric": "without_explicit_higher_education_count", "value": 1},
                ]
            ).to_csv(csv_dir / "education_requirements_summary.csv", index=False)
            pd.DataFrame(
                [
                    {"metric": "published_total", "value": 3},
                    {"metric": "closed_total", "value": 1},
                    {"metric": "latest_publication_date", "value": "2026-04-21"},
                    {"metric": "published_30d", "value": 2},
                    {"metric": "published_previous_30d", "value": 1},
                    {"metric": "growth_30d", "value": 1.0},
                ]
            ).to_csv(csv_dir / "vacancy_trends_summary.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "date": "2026-04-20",
                        "published_count": 1,
                        "closed_count": 0,
                        "net_change": 1,
                        "growth_rate": None,
                    },
                    {
                        "date": "2026-04-21",
                        "published_count": 2,
                        "closed_count": 1,
                        "net_change": 1,
                        "growth_rate": 1.0,
                    },
                ]
            ).to_csv(csv_dir / "vacancy_trends_daily.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "week_start": "2026-04-20",
                        "published_count": 3,
                        "closed_count": 1,
                        "net_change": 2,
                        "growth_rate": None,
                    },
                ]
            ).to_csv(csv_dir / "vacancy_trends_weekly.csv", index=False)
            pd.DataFrame(
                [{"month": 4, "vacancy_count": 3, "share": 1.0}]
            ).to_csv(csv_dir / "vacancy_trends_monthly.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "date": "2026-04-20",
                        "canton": "ZH",
                        "role_category": "data_ai",
                        "published_count": 1,
                        "closed_count": 0,
                        "net_change": 1,
                    },
                    {
                        "date": "2026-04-21",
                        "canton": "BE",
                        "role_category": "software_engineering",
                        "published_count": 2,
                        "closed_count": 1,
                        "net_change": 1,
                    },
                ]
            ).to_csv(csv_dir / "vacancy_trends_segments_daily.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "week_start": "2026-04-20",
                        "canton": "ZH",
                        "role_category": "data_ai",
                        "published_count": 3,
                        "closed_count": 1,
                        "net_change": 2,
                    },
                ]
            ).to_csv(csv_dir / "vacancy_trends_segments_weekly.csv", index=False)
            pd.DataFrame(
                [
                    {"metric": "salary_count", "value": 2},
                    {"metric": "salary_coverage", "value": 0.6667},
                    {"metric": "average_salary", "value": 115000},
                    {"metric": "median_salary", "value": 115000},
                    {"metric": "currency", "value": "CHF"},
                    {"metric": "unit", "value": "YEAR"},
                ]
            ).to_csv(csv_dir / "salary_summary.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "role_category": "data_ai",
                        "salary_count": 2,
                        "average_salary": 115000,
                        "median_salary": 115000,
                        "min_salary": 100000,
                        "max_salary": 130000,
                        "rank": 1,
                    }
                ]
            ).to_csv(csv_dir / "salary_by_role_category.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "seniority": "senior",
                        "salary_count": 2,
                        "average_salary": 115000,
                        "median_salary": 115000,
                        "min_salary": 100000,
                        "max_salary": 130000,
                        "rank": 1,
                    }
                ]
            ).to_csv(csv_dir / "salary_by_seniority.csv", index=False)
            pd.DataFrame(
                [
                    {"skill": "python", "vacancy_count": 2, "share": 0.6667},
                    {"skill": "sql", "vacancy_count": 1, "share": 0.3333},
                ]
            ).to_csv(csv_dir / "top_skills_overall.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "role_category": "data_ai",
                        "skill": "python",
                        "vacancy_count": 2,
                        "share_within_group": 1.0,
                        "rank": 1,
                    }
                ]
            ).to_csv(csv_dir / "top_skills_by_role_category.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "canton": "ZH",
                        "skill": "python",
                        "vacancy_count": 2,
                        "share_within_group": 1.0,
                        "rank": 1,
                    }
                ]
            ).to_csv(csv_dir / "top_skills_by_canton.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "company": "Acme",
                        "vacancy_count": 2,
                        "share": 0.6667,
                    },
                    {
                        "company": "Beta",
                        "vacancy_count": 1,
                        "share": 0.3333,
                    },
                ]
            ).to_csv(csv_dir / "distribution_company.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "role_category": "data_ai",
                        "vacancy_count": 2,
                        "share": 0.6667,
                    }
                ]
            ).to_csv(csv_dir / "distribution_role_category.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "canton": "ZH",
                        "vacancy_count": 2,
                        "share": 0.6667,
                    }
                ]
            ).to_csv(csv_dir / "distribution_canton.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "skill_1": "python",
                        "skill_2": "sql",
                        "vacancy_count": 1,
                    }
                ]
            ).to_csv(csv_dir / "skill_cooccurrence_pairs.csv", index=False)

            saved_paths = build_public_stats.build_public_snapshots(
                csv_dir=csv_dir,
                output_dir=output_dir,
                copy_csv_dir=copy_csv_dir,
            )

            self.assertTrue(saved_paths)
            overview = json.loads((output_dir / "overview.json").read_text(encoding="utf-8"))
            self.assertTrue(overview["available"])
            self.assertEqual(3, overview["metrics"]["total_vacancies"])

            education_requirements = json.loads(
                (output_dir / "education_requirements.json").read_text(encoding="utf-8")
            )
            self.assertTrue(education_requirements["available"])
            self.assertEqual(
                2,
                education_requirements["summary"]["higher_education_vacancy_count"],
            )
            self.assertEqual(
                0.6667,
                education_requirements["summary"]["higher_education_vacancy_share"],
            )

            vacancy_trends = json.loads(
                (output_dir / "vacancy_trends.json").read_text(encoding="utf-8")
            )
            self.assertTrue(vacancy_trends["available"])
            self.assertEqual(3, vacancy_trends["summary"]["published_total"])
            self.assertEqual(2, vacancy_trends["summary"]["published_30d"])
            self.assertEqual("2026-04-21", vacancy_trends["daily"][1]["date"])
            self.assertEqual("ZH", vacancy_trends["segments"]["daily"][0]["canton"])
            self.assertEqual(
                "data_ai",
                vacancy_trends["segments"]["weekly"][0]["role_category"],
            )
            self.assertEqual(4, vacancy_trends["seasonality"]["monthly"][0]["month"])

            salary_metrics = json.loads(
                (output_dir / "salary_metrics.json").read_text(encoding="utf-8")
            )
            self.assertTrue(salary_metrics["available"])
            self.assertEqual(115000, salary_metrics["summary"]["average_salary"])
            self.assertEqual("data_ai", salary_metrics["by_role_category"][0]["role_category"])
            self.assertEqual("senior", salary_metrics["by_seniority"][0]["seniority"])

            top_skills = json.loads((output_dir / "top_skills.json").read_text(encoding="utf-8"))
            self.assertEqual("python", top_skills["overall"][0]["skill"])
            self.assertEqual("data_ai", top_skills["by_role_category"][0]["group"])

            canton_distribution = json.loads(
                (output_dir / "distributions_canton.json").read_text(encoding="utf-8")
            )
            self.assertEqual("ZH", canton_distribution["items"][0]["key"])

            company_distribution = json.loads(
                (output_dir / "distributions_company.json").read_text(encoding="utf-8")
            )
            self.assertEqual("Acme", company_distribution["items"][0]["key"])
            self.assertEqual(2, company_distribution["items"][0]["vacancy_count"])

            self.assertTrue((copy_csv_dir / "overview_metrics.csv").exists())
            self.assertTrue((copy_csv_dir / "education_requirements_summary.csv").exists())
            self.assertTrue((copy_csv_dir / "vacancy_trends_daily.csv").exists())
            self.assertTrue((copy_csv_dir / "vacancy_trends_segments_weekly.csv").exists())
            self.assertTrue((copy_csv_dir / "salary_summary.csv").exists())
            self.assertTrue((copy_csv_dir / "salary_by_seniority.csv").exists())

    def test_build_public_snapshots_marks_missing_csv_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_dir = temp_path / "analytics_output"
            output_dir = temp_path / "public_stats" / "data"
            csv_dir.mkdir(parents=True)

            build_public_stats.build_public_snapshots(
                csv_dir=csv_dir,
                output_dir=output_dir,
                copy_csv_dir=None,
            )

            metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
            overview = json.loads((output_dir / "overview.json").read_text(encoding="utf-8"))

            self.assertIn("overview_metrics.csv", metadata["missing_csv_files"])
            self.assertFalse(overview["available"])
            self.assertEqual({}, overview["metrics"])


if __name__ == "__main__":
    unittest.main()

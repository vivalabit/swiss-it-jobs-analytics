from __future__ import annotations

import unittest

from jobs_ch.analytics import build_job_analytics
from jobs_ch.models import VacancyFull


class JobsChAnalyticsTests(unittest.TestCase):
    def test_build_job_analytics_extracts_market_signals(self) -> None:
        vacancy = VacancyFull(
            id="analytics-1",
            title="Senior Data Engineer",
            company="Acme",
            place="Zurich",
            description_text=(
                "Build Python and SQL pipelines with dbt, Airflow and Snowflake on AWS. "
                "Work with Docker, Kubernetes and GitLab CI/CD in a hybrid setup with home office. "
                "Fluent English and German required."
            ),
            raw={
                "employmentGrades": [80, 100],
                "listingTags": [{"name": "quickApply"}],
            },
            job_posting_schema={
                "@type": "JobPosting",
                "employmentType": ["FULL_TIME"],
                "occupationalCategory": "Data Engineering",
                "industry": "Information Technology",
                "hiringOrganization": {
                    "name": "Acme",
                    "sameAs": "https://example.com",
                },
                "jobLocation": {
                    "address": {
                        "addressLocality": "Zurich",
                        "postalCode": "8000",
                        "addressCountry": "Switzerland",
                    }
                },
                "baseSalary": {
                    "currency": "CHF",
                    "value": {
                        "minValue": 120000,
                        "maxValue": 140000,
                        "unitText": "YEAR",
                    },
                },
            },
        )

        analytics = build_job_analytics(vacancy)

        self.assertEqual("data_ai", analytics["role_family_primary"])
        self.assertIn("senior", analytics["seniority_labels"])
        self.assertIn("python", analytics["programming_languages"])
        self.assertIn("sql", analytics["programming_languages"])
        self.assertIn("dbt", analytics["frameworks_libraries"])
        self.assertIn("aws", analytics["cloud_platforms"])
        self.assertIn("snowflake", analytics["data_platforms"])
        self.assertIn("airflow", analytics["frameworks_libraries"])
        self.assertIn("english", analytics["spoken_languages"])
        self.assertIn("german", analytics["spoken_languages"])
        self.assertEqual("hybrid", analytics["remote_mode"])
        self.assertEqual({"min": 80, "max": 100}, analytics["workload_percent"])
        self.assertEqual("CHF", analytics["salary"]["currency"])
        self.assertEqual(120000, analytics["salary"]["min"])
        self.assertEqual(["quickApply"], analytics["listing_tags"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from swiss_jobs.providers.jobup_ch.extractors import (
    extract_detail_payload,
    parse_jobs_from_search_page,
)

SEARCH_HTML = """
<html>
  <head>
    <title>41 Software engineer job ads in Zurich found on jobup.ch</title>
  </head>
  <body>
    <script>
      __GLOBAL__ = {"DEFAULT_SEARCH_RESULTS":20};
      __INIT__ = {
        "vacancy": {
          "results": {
            "main": {
              "results": [
                {
                  "id": "job-1",
                  "title": "Software Engineer",
                  "company": {"name": "Acme AG"},
                  "place": "Zurich",
                  "publicationDate": "2026-04-10T09:00:00+02:00",
                  "initialPublicationDate": "2026-04-10T08:00:00+02:00",
                  "isNew": true,
                  "employmentGrades": [80, 100],
                  "listingTags": [{"name": "quickApply"}]
                },
                {
                  "id": "job-2",
                  "title": "Data Engineer",
                  "company": {"name": "Beta GmbH"},
                  "place": "Bern",
                  "publicationDate": "2026-04-09T09:00:00+02:00",
                  "initialPublicationDate": "2026-04-09T08:00:00+02:00",
                  "isNew": false,
                  "employmentGrades": [100, 100],
                  "listingTags": []
                }
              ],
              "meta": {"numPages": 3, "totalHits": 41}
            }
          }
        }
      };
    </script>
  </body>
</html>
"""

NEW_HTML = """
<html>
  <body>
    <script>
      __GLOBAL__ = {"DEFAULT_SEARCH_RESULTS":20};
      __INIT__ = {
        "vacancy": {
          "results": {
            "newVacancies": {
              "results": [
                {
                  "id": "job-new-1",
                  "title": "Platform Engineer",
                  "company": {"name": "Gamma SA"},
                  "place": "Lausanne",
                  "publicationDate": "2026-04-13T10:00:00+02:00",
                  "initialPublicationDate": "2026-04-13T10:00:00+02:00",
                  "isNew": true,
                  "employmentGrades": [100, 100],
                  "listingTags": [{"name": "easyApply"}]
                }
              ],
              "meta": {"numPages": 12, "totalHits": 240}
            }
          }
        }
      };
    </script>
  </body>
</html>
"""

DETAIL_HTML = """
<html>
  <head>
    <script type="application/ld+json">
      [
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Software Engineer",
          "description": "<p>Build APIs in Python.</p><ul><li>FastAPI</li></ul>",
          "datePosted": "2026-04-10T09:00:00+02:00",
          "employmentType": ["FULL_TIME"]
        }
      ]
    </script>
  </head>
  <body>
    <span class="d_inline-block mr_s8 textStyle_caption1">
      CHF 43'750 - 70'000/an
    </span>
    <div>Estimation salariale de jobup.ch</div>
  </body>
</html>
"""


class JobupChExtractorsTests(unittest.TestCase):
    def test_parse_search_page_extracts_jobs_and_pages(self) -> None:
        jobs, total_pages = parse_jobs_from_search_page(
            SEARCH_HTML,
            base_url="https://www.jobup.ch",
            mode="search",
        )

        self.assertEqual(2, len(jobs))
        self.assertEqual(3, total_pages)
        self.assertEqual("job-1", jobs[0].id)
        self.assertEqual("Software Engineer", jobs[0].title)
        self.assertEqual("Acme AG", jobs[0].company)
        self.assertEqual("Zurich", jobs[0].place)
        self.assertEqual("jobup.ch", jobs[0].source)
        self.assertEqual("80% - 100%", jobs[0].raw["workload"])
        self.assertEqual([{"name": "quickApply"}], jobs[0].raw["listingTags"])
        self.assertTrue(jobs[0].is_new)

    def test_parse_new_page_uses_new_vacancies_bucket(self) -> None:
        jobs, total_pages = parse_jobs_from_search_page(
            NEW_HTML,
            base_url="https://www.jobup.ch",
            mode="new",
        )

        self.assertEqual(1, len(jobs))
        self.assertEqual(12, total_pages)
        self.assertEqual("job-new-1", jobs[0].id)
        self.assertEqual("100%", jobs[0].raw["workload"])

    def test_extract_detail_payload_extracts_schema(self) -> None:
        payload = extract_detail_payload(DETAIL_HTML)

        self.assertEqual(["FULL_TIME"], payload["job_posting_schema"]["employmentType"])
        self.assertIn("Build APIs in Python", payload["description_text"])
        self.assertEqual("CHF", payload["salary"]["currency"])
        self.assertEqual(43750, payload["salary"]["range"]["minValue"])
        self.assertEqual(70000, payload["salary"]["range"]["maxValue"])
        self.assertEqual("YEAR", payload["salary"]["unit"])
        self.assertEqual("CHF 43750-70000 / year", payload["salary_text"])


if __name__ == "__main__":
    unittest.main()

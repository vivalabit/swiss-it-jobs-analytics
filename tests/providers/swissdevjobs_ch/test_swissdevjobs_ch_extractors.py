from __future__ import annotations

import unittest

from swiss_jobs.providers.swissdevjobs_ch.extractors import (
    extract_detail_payload,
    parse_jobs_from_feed,
)

SEARCH_PAYLOAD = [
    {
        "_id": "69b26ee4adc9b2ac7f28a545",
        "jobUrl": "CONVOTIS-Schweiz-AG-Senior-Kubernetes-Platform-Engineer--DevOps-Engineer-a-80---100",
        "isPaused": False,
        "company": "CONVOTIS Schweiz AG",
        "name": "Senior Kubernetes Platform Engineer / DevOps Engineer (a) 80 - 100%",
        "activeFrom": "2026-04-15T08:33:05.175+02:00",
        "actualCity": "Zürich",
        "cityCategory": "Zurich",
        "jobType": "Full-Time",
        "workplace": "hybrid",
        "annualSalaryFrom": 100000,
        "annualSalaryTo": 130000,
        "technologies": ["Kubernetes", "GitLab"],
        "filterTags": ["CI/CD", "Cloud", "DevOps"],
        "companyWebsiteLink": "convotis.ch"
    },
    {
        "_id": "69cce1f972bcc36c639d272f",
        "jobUrl": "mesoneer-AG-DevOps-Engineer",
        "isPaused": False,
        "company": "mesoneer AG",
        "name": "DevOps Engineer",
        "activeFrom": "2026-04-15T07:02:04.870+00:00",
        "actualCity": "Wallisellen",
        "cityCategory": "Zurich",
        "jobType": "Full-Time",
        "workplace": "hybrid",
        "annualSalaryFrom": 80000,
        "annualSalaryTo": 120000,
        "technologies": ["DevOps"],
        "filterTags": ["Cloud", "Kubernetes"]
    },
    {
        "_id": "old-1",
        "jobUrl": "old-role",
        "isPaused": False,
        "deactivatedOn": "2026-04-10",
        "company": "Old Co",
        "name": "Old Role",
        "activeFrom": "2026-03-01T00:00:00.000+02:00",
        "actualCity": "Bern",
        "cityCategory": "Bern"
    }
]

DETAIL_HTML = """
<!doctype html>
<html>
  <head>
    <script>
      window.__detailedJob={
        "_id":"69b26ee4adc9b2ac7f28a545",
        "jobUrl":"CONVOTIS-Schweiz-AG-Senior-Kubernetes-Platform-Engineer--DevOps-Engineer-a-80---100",
        "activeFrom":"2026-04-15T08:33:05.175+02:00",
        "company":"CONVOTIS Schweiz AG",
        "companyWebsiteLink":"convotis.ch",
        "logoImg":"convotis-swiss-cloud-ag-logo-1744190042727.jpg",
        "workplace":"hybrid",
        "language":"German",
        "candidateContactWay":"CompanyWebsite",
        "companyType":"Services",
        "companySize":"50-200",
        "hasVisaSponsorship":"No",
        "address":"Weberstrasse 4",
        "actualCity":"Zürich",
        "postalCode":"8004",
        "name":"Senior Kubernetes Platform Engineer / DevOps Engineer (a) 80 - 100%",
        "jobType":"Full-Time",
        "techCategory":"DevOps",
        "metaCategory":"clouddevops",
        "annualSalaryFrom":100000,
        "annualSalaryTo":130000,
        "technologies":["CI/CD","Cloud","DevOps","GitLab","Kubernetes"],
        "filterTags":["CI/CD","Cloud","DevOps","GitLab","Kubernetes"],
        "metScrum":true,
        "metCodeReviews":true,
        "metUnitTests":true,
        "description":"Standort: Zürich oder hybrid innerhalb der Schweiz.\\n\\nWir bauen Plattformen.",
        "requirementsMustTextArea":"- Kubernetes\\n- GitLab",
        "responsibilitiesTextArea":"- Build platform\\n- Improve reliability",
        "perkKeys":["cooloffice","remote3day"]
      }
    </script>
  </head>
  <body></body>
</html>
"""


class SwissDevJobsChExtractorsTests(unittest.TestCase):
    def test_parse_feed_filters_inactive_jobs_and_builds_vacancies(self) -> None:
        jobs, total_pages = parse_jobs_from_feed(
            SEARCH_PAYLOAD,
            base_url="https://swissdevjobs.ch",
            mode="search",
            term="devops engineer",
            location="zurich",
            max_pages=0,
        )

        self.assertEqual(2, len(jobs))
        self.assertEqual(1, total_pages)
        self.assertEqual("69b26ee4adc9b2ac7f28a545", jobs[0].id)
        self.assertEqual("CONVOTIS Schweiz AG", jobs[0].company)
        self.assertEqual("Zürich", jobs[0].place)
        self.assertEqual("swissdevjobs.ch", jobs[0].source)
        self.assertEqual("100000 - 130000", jobs[0].raw["salaryText"].replace("CHF ", "").replace(" / year", ""))
        self.assertEqual("80% - 100%", jobs[0].raw["workload"])
        self.assertEqual(["CI/CD", "Cloud", "DevOps"], jobs[0].raw["listingTags"])

    def test_extract_detail_payload_builds_schema_and_description(self) -> None:
        payload = extract_detail_payload(
            DETAIL_HTML,
            page_url="https://swissdevjobs.ch/jobs/CONVOTIS-Schweiz-AG-Senior-Kubernetes-Platform-Engineer--DevOps-Engineer-a-80---100",
        )

        self.assertEqual("JobPosting", payload["job_posting_schema"]["@type"])
        self.assertEqual("Full-Time", payload["job_posting_schema"]["employmentType"])
        self.assertEqual("2026-04-15T08:33:05.175+02:00", payload["detail_attributes"]["publicationDate"])
        self.assertEqual("CHF 100000 - 130000 / year", payload["detail_attributes"]["salaryText"])
        self.assertIn("Requirements", payload["description_html"])
        self.assertIn("Build platform", payload["description_text"])


if __name__ == "__main__":
    unittest.main()

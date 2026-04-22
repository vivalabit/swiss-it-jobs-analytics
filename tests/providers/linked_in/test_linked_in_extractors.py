from __future__ import annotations

import unittest

from swiss_jobs.providers.linked_in.extractors import (
    extract_detail_payload,
    parse_jobs_from_search_page,
)

SEARCH_HTML = """
<html>
  <body>
    <ul>
      <li class="jobs-search-results__list-item" data-occludable-job-id="4211112222">
        <div class="job-card-container">
          <a class="job-card-container__link job-card-list__title--link"
             href="/jobs/view/software-engineer-4211112222/?trackingId=abc">
            <span class="job-card-list__title">Software Engineer</span>
          </a>
          <div class="job-card-container__primary-description">Acme AG</div>
          <ul class="job-card-container__metadata-wrapper">
            <li class="job-card-container__metadata-item">Zurich, Switzerland</li>
          </ul>
          <time datetime="2026-04-20">2 days ago</time>
        </div>
      </li>
      <li class="jobs-search-results__list-item">
        <div class="job-card-container">
          <a class="job-card-container__link"
             href="https://www.linkedin.com/jobs/view/4211113333/">
            Data Engineer
          </a>
          <div class="job-card-container__primary-description">Example GmbH</div>
          <div class="job-card-container__metadata-item">Winterthur, Switzerland</div>
          <span class="job-card-container__listed-time">New</span>
        </div>
      </li>
    </ul>
  </body>
</html>
"""

DETAIL_HTML = """
<html>
  <head>
    <script type="application/ld+json" nonce="abc">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Software Engineer",
        "description": "<p>Build services with Python and PostgreSQL.</p>",
        "datePosted": "2026-04-20",
        "employmentType": "FULL_TIME"
      }
    </script>
  </head>
  <body>
    <div class="jobs-description__content">
      <p>Build services with Python and PostgreSQL.</p>
    </div>
  </body>
</html>
"""


class LinkedInExtractorsTests(unittest.TestCase):
    def test_parse_search_page_extracts_cards(self) -> None:
        jobs = parse_jobs_from_search_page(SEARCH_HTML, base_url="https://www.linkedin.com")

        self.assertEqual(2, len(jobs))
        self.assertEqual("4211112222", jobs[0].id)
        self.assertEqual("Software Engineer", jobs[0].title)
        self.assertEqual("Acme AG", jobs[0].company)
        self.assertEqual("Zurich, Switzerland", jobs[0].place)
        self.assertEqual("2026-04-20", jobs[0].publication_date)
        self.assertEqual("https://www.linkedin.com/jobs/view/4211112222/", jobs[0].url)
        self.assertEqual("linkedin.com", jobs[0].source)
        self.assertTrue(jobs[1].is_new)

    def test_extract_detail_payload_extracts_schema_description(self) -> None:
        payload = extract_detail_payload(DETAIL_HTML)

        self.assertEqual("FULL_TIME", payload["job_posting_schema"]["employmentType"])
        self.assertIn("Python and PostgreSQL", payload["description_text"])


if __name__ == "__main__":
    unittest.main()


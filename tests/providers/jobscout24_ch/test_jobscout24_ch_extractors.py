from __future__ import annotations

import unittest

from swiss_jobs.providers.jobscout24_ch.extractors import (
    extract_detail_payload,
    parse_jobs_from_search_page,
)

SEARCH_HTML = """
<html>
  <body>
    <ul>
      <li class="job-list-item " data-job-id="10113394" data-job-detail-url="/en/job/cb4c3f58-769f-486c-aeeb-aeb2dca357f0/">
        <div class="upper-line">
          <a href="/en/job/cb4c3f58-769f-486c-aeeb-aeb2dca357f0/" class="job-link-detail job-title" title="Software Engineer (a)">Software Engineer (a)</a>
        </div>
        <p class="job-attributes"><span>Stöcklin Logistik AG</span>, <span>Jona</span></p>
        <div class="lower-line">
          <div class="job-tags">
            <ul>
              <li><span class="tag tag-readonly">80% - 100%</span></li>
              <li><span class="tag tag-readonly">Large companies</span></li>
            </ul>
          </div>
          <p class="job-date">5 d</p>
        </div>
      </li>
      <li class="job-list-item " data-job-id="9980485" data-job-detail-url="/en/job/a72bdd36-85b0-424c-b8d2-515635813f38/">
        <div class="upper-line">
          <a href="/en/job/a72bdd36-85b0-424c-b8d2-515635813f38/" class="job-link-detail job-title" title="QT Software Engineer 80-100% (m/w/d)">QT Software Engineer 80-100% (m/w/d)</a>
        </div>
        <p class="job-attributes"><span>Bucher Municipal AG</span>, <span>Niederweningen</span></p>
        <div class="lower-line new">
          <div class="job-tags"><ul><li><span class="tag tag-readonly">100%</span></li></ul></div>
          <p class="job-date">New</p>
        </div>
      </li>
    </ul>
    <div class="pagination"><div class="pages"><ul><li>Page 1 / 52</li></ul></div></div>
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
          "title": "Software Engineer (a)",
          "description": "<p>Build backend services in Java.</p><ul><li>Spring Boot</li><li>Oracle</li></ul>",
          "datePosted": "2026-04-07T13:05:03.4570000",
          "employmentType": ["FULL_TIME", "PART_TIME"]
        }
      ]
    </script>
  </head>
  <body>
    <article class="job-details"
      data-job-id="10113394"
      data-pub-date="2026-04-07T11:05:03+02:00:00"
      data-employment-grade="80% - 100%"
      data-employment-type="permanent position"
      data-job-position="specialist"
      data-job-location="jona">
    </article>
    <div class="job-description">
      <div id="slim"><div class="slim_content"><div class="slim_text"><p>Build backend services in Java.</p></div></div></div>
    </div>
  </body>
</html>
"""


class JobScout24ChExtractorsTests(unittest.TestCase):
    def test_parse_search_page_extracts_jobs_and_pages(self) -> None:
        jobs, total_pages = parse_jobs_from_search_page(SEARCH_HTML, base_url="https://www.jobscout24.ch")

        self.assertEqual(2, len(jobs))
        self.assertEqual(52, total_pages)
        self.assertEqual("10113394", jobs[0].id)
        self.assertEqual("Software Engineer (a)", jobs[0].title)
        self.assertEqual("Stöcklin Logistik AG", jobs[0].company)
        self.assertEqual("Jona", jobs[0].place)
        self.assertEqual("5 d", jobs[0].publication_date)
        self.assertEqual("jobscout24.ch", jobs[0].source)
        self.assertEqual("80% - 100%", jobs[0].raw["workload"])

        self.assertTrue(jobs[1].is_new)

    def test_extract_detail_payload_extracts_schema_and_attributes(self) -> None:
        payload = extract_detail_payload(DETAIL_HTML)

        self.assertEqual(["FULL_TIME", "PART_TIME"], payload["job_posting_schema"]["employmentType"])
        self.assertIn("Build backend services", payload["description_text"])
        self.assertEqual("80% - 100%", payload["detail_attributes"]["employmentGrade"])
        self.assertEqual("permanent position", payload["detail_attributes"]["employmentTypeText"])


if __name__ == "__main__":
    unittest.main()

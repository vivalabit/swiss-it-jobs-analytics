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
    <h1 class="jobs-unified-top-card__job-title">Software Engineer</h1>
    <a class="jobs-unified-top-card__company-name" href="/company/acme/">Acme AG</a>
    <div class="jobs-unified-top-card__primary-description-without-tagline">
      Acme AG · Zurich, Switzerland · 2 days ago
    </div>
    <div class="jobs-unified-top-card__job-insight">100 applicants</div>
    <div class="jobs-unified-top-card__job-insight">Hybrid</div>
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
        self.assertEqual("linkedin:4211112222", jobs[0].id)
        self.assertEqual("4211112222", jobs[0].raw["linkedinJobId"])
        self.assertEqual("Software Engineer", jobs[0].title)
        self.assertEqual("Acme AG", jobs[0].company)
        self.assertEqual("Zurich, Switzerland", jobs[0].place)
        self.assertEqual("2026-04-20", jobs[0].publication_date)
        self.assertEqual("https://www.linkedin.com/jobs/view/4211112222/", jobs[0].url)
        self.assertEqual("linkedin.com", jobs[0].source)
        self.assertTrue(jobs[1].is_new)

    def test_parse_rendered_job_card_list_markup(self) -> None:
        html = """
        <html>
          <body>
            <div class="display-flex job-card-container relative job-card-list job-card-container--clickable"
                 data-job-id="4288887777">
              <a class="job-card-list__title--link"
                 href="/jobs/collections/recommended/?currentJobId=4288887777">
                <strong>Software Engineer</strong>
                <span>with verification</span>
              </a>
              <div class="artdeco-entity-lockup__subtitle">Algorized</div>
              <div class="artdeco-entity-lockup__caption">Etoy, Vaud, Switzerland (On-site) Actively Hiring 4 days ago</div>
              <time datetime="2026-03-20">1 month ago</time>
            </div>
          </body>
        </html>
        """

        jobs = parse_jobs_from_search_page(html, base_url="https://www.linkedin.com")

        self.assertEqual(1, len(jobs))
        self.assertEqual("linkedin:4288887777", jobs[0].id)
        self.assertEqual("4288887777", jobs[0].raw["linkedinJobId"])
        self.assertEqual("Software Engineer", jobs[0].title)
        self.assertEqual("Algorized", jobs[0].company)
        self.assertEqual("Etoy, Vaud, Switzerland (On-site)", jobs[0].place)
        self.assertEqual("https://www.linkedin.com/jobs/view/4288887777/", jobs[0].url)
        self.assertIn("cardText", jobs[0].raw)

    def test_extract_detail_payload_extracts_schema_description(self) -> None:
        payload = extract_detail_payload(DETAIL_HTML)

        self.assertEqual("FULL_TIME", payload["job_posting_schema"]["employmentType"])
        self.assertIn("Python and PostgreSQL", payload["description_text"])
        self.assertEqual("Software Engineer", payload["title"])
        self.assertEqual("Acme AG", payload["company"])
        self.assertEqual("Zurich, Switzerland", payload["place"])
        self.assertEqual("Hybrid", payload["detail_attributes"]["workplace"])
        self.assertEqual("100 applicants", payload["detail_attributes"]["applicantCountText"])
        self.assertEqual("2 days ago", payload["posted_at_text"])

    def test_extract_detail_payload_prefers_right_detail_panel(self) -> None:
        html = """
        <html>
          <body>
            <div class="scaffold-layout__list">
              <div class="job-card-container" data-job-id="4111111111">
                <a class="job-card-list__title--link" href="/jobs/view/4111111111/">
                  Wrong Left List Title
                </a>
                <div class="job-card-container__primary-description">Wrong Left Company</div>
              </div>
            </div>
            <main class="jobs-search__job-details--container">
              <h1 class="job-details-jobs-unified-top-card__job-title">Right Panel Engineer</h1>
              <div class="job-details-jobs-unified-top-card__company-name">
                <a href="/company/right/">Right Panel AG</a>
              </div>
              <div class="job-details-jobs-unified-top-card__primary-description-container">
                Right Panel AG · Zurich, Switzerland · 1 day ago · Over 100 applicants
              </div>
              <button class="job-details-preferences-and-skills__pill">Remote</button>
              <section class="jobs-description__container">
                <div id="job-details">
                  <p>Right panel description with Python and APIs.</p>
                </div>
              </section>
            </main>
          </body>
        </html>
        """

        payload = extract_detail_payload(html)

        self.assertEqual("Right Panel Engineer", payload["title"])
        self.assertEqual("Right Panel AG", payload["company"])
        self.assertEqual("Zurich, Switzerland", payload["place"])
        self.assertEqual("1 day ago", payload["posted_at_text"])
        self.assertIn("Right panel description", payload["description_text"])
        self.assertEqual("Remote", payload["detail_attributes"]["workplace"])


if __name__ == "__main__":
    unittest.main()

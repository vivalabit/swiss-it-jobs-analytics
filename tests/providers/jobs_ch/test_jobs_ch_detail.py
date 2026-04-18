from __future__ import annotations

import unittest

from swiss_jobs.core.models import VacancyFull
from swiss_jobs.providers.jobs_ch.detail import apply_detail_payload, extract_detail_payload


DETAIL_HTML = """
<html>
  <head>
    <script type="application/ld+json">
      {
        "@type": "JobPosting",
        "title": "Junior/Mid Python Developer",
        "description": "<p>Build Python services.</p>"
      }
    </script>
  </head>
  <body>
    <li data-cy="info-salary" class="ai_flex-stx">
      <div>
        <span class="d_inline-block mr_s8 textStyle_caption1">
          CHF 52 000 - 92 000/year
        </span>
        <div>Salary estimate from jobs.ch</div>
      </div>
    </li>
  </body>
</html>
"""


class JobsChDetailTests(unittest.TestCase):
    def test_extract_detail_payload_parses_salary_from_html_block(self) -> None:
        payload = extract_detail_payload(DETAIL_HTML)

        salary = payload["salary"]
        self.assertIsInstance(salary, dict)
        assert isinstance(salary, dict)
        self.assertEqual("CHF", salary["currency"])
        self.assertEqual(52000, salary["range"]["minValue"])
        self.assertEqual(92000, salary["range"]["maxValue"])
        self.assertEqual("YEAR", salary["unit"])
        self.assertEqual("CHF 52000-92000 / year", payload["salary_text"])

        schema = payload["job_posting_schema"]
        self.assertIsInstance(schema, dict)
        assert isinstance(schema, dict)
        self.assertEqual("CHF", schema["baseSalary"]["currency"])
        self.assertEqual(52000, schema["baseSalary"]["value"]["minValue"])
        self.assertEqual(92000, schema["baseSalary"]["value"]["maxValue"])
        self.assertEqual("YEAR", schema["baseSalary"]["value"]["unitText"])

    def test_apply_detail_payload_writes_salary_to_vacancy_raw(self) -> None:
        vacancy = VacancyFull(
            id="vac-1",
            title="Junior/Mid Python Developer",
            url="https://www.jobs.ch/en/vacancies/detail/vac-1/",
        )

        apply_detail_payload(vacancy, extract_detail_payload(DETAIL_HTML))

        self.assertEqual("CHF 52000-92000 / year", vacancy.raw["salaryText"])
        self.assertEqual("CHF", vacancy.raw["salary"]["currency"])
        self.assertEqual(52000, vacancy.raw["salary"]["range"]["minValue"])
        self.assertEqual(92000, vacancy.raw["salary"]["range"]["maxValue"])


if __name__ == "__main__":
    unittest.main()

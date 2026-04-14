from __future__ import annotations

import unittest
from unittest.mock import patch

from swiss_jobs.core.models import VacancyFull
from swiss_jobs.providers.jobs_ch.client import JobsChHttpClient


class _StubJobsChHttpClient(JobsChHttpClient):
    def _get_init_state(self, session, url, params):  # noqa: ANN001
        if params:
            query = "&".join(f"{key}={value}" for key, value in params.items())
            response_url = f"{url}?{query}"
        else:
            response_url = url
        return {"dummy": True}, response_url


class JobsChHttpClientTests(unittest.TestCase):
    def test_fetch_query_sets_search_url_from_response(self) -> None:
        client = _StubJobsChHttpClient()
        vacancy = VacancyFull(
            id="vac-1",
            title="Software Engineer",
            url="https://example.test/jobs/1",
        )

        with (
            patch(
                "swiss_jobs.providers.jobs_ch.client.get_results_bucket",
                return_value={"meta": {"numPages": 1}},
            ),
            patch(
                "swiss_jobs.providers.jobs_ch.client.parse_jobs_from_bucket",
                return_value=[vacancy],
            ),
        ):
            result = client._fetch_query(
                session=client._new_session(),
                mode="search",
                term="software engineer",
                location="zurich",
                max_pages=1,
                show_progress=False,
                query_label="query 1/1",
            )

        self.assertEqual(1, len(result))
        self.assertEqual(
            "https://www.jobs.ch/en/vacancies/?term=software engineer&location=zurich",
            result[0].raw["search_url"],
        )
        self.assertEqual(
            {"term": "software engineer", "location": "zurich"},
            result[0].raw["search_params"],
        )


if __name__ == "__main__":
    unittest.main()

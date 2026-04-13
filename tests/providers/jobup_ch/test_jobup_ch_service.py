from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from swiss_jobs.core.models import ClientConfig, VacancyFull
from swiss_jobs.providers.jobup_ch.client import JobupChHttpClient
from swiss_jobs.providers.jobup_ch.service import JobupChParserService


class FakeJobupChClient:
    def __init__(self, vacancies: list[VacancyFull]) -> None:
        self._vacancies = [vacancy.to_dict() for vacancy in vacancies]
        self.enrich_calls = 0

    def search(self, config: ClientConfig, queries):  # noqa: ANN001
        return [VacancyFull.from_dict(item) for item in self._vacancies], [], len(queries)

    def enrich_vacancies(self, vacancies, *, detail_limit, detail_workers, show_progress):  # noqa: ANN001
        self.enrich_calls += 1
        for vacancy in vacancies:
            vacancy.description_text = vacancy.description_text or "Detailed description"
        return len(vacancies), len(vacancies)


def make_config(payload: dict) -> ClientConfig:
    return ClientConfig.from_dict(payload, source="<test-config>", default_client_id="main-config")


class JobupChServiceTests(unittest.TestCase):
    def test_client_builds_search_params(self) -> None:
        client = JobupChHttpClient()
        params = client._build_query_params(  # noqa: SLF001
            mode="search",
            term="software engineer",
            location="zurich",
            page=2,
        )
        self.assertEqual(
            {"term": "software engineer", "location": "zurich", "page": "2"},
            params,
        )

    def test_client_state_is_isolated(self) -> None:
        vacancy = VacancyFull(
            id="shared-1",
            title="Python Developer",
            company="Acme",
            place="Zurich",
            url="https://www.jobup.ch/en/jobs/detail/shared-1/",
            source="jobup.ch",
        )
        fake_client = FakeJobupChClient([vacancy])

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_root = Path(tmpdir) / "runtime"
            base_config = {
                "mode": "search",
                "terms": ["python developer"],
                "locations": ["zurich"],
                "skip_detail_schema": True,
                "output_format": "brief",
            }
            config_a = make_config({"client_id": "client_a", "database_path": str(runtime_root / "client-a.sqlite"), **base_config})
            config_b = make_config({"client_id": "client_b", "database_path": str(runtime_root / "client-b.sqlite"), **base_config})

            service = JobupChParserService(http_client=fake_client, runtime_root=runtime_root)

            first_a = service.run(config_a)
            first_b = service.run(config_b)
            second_a = service.run(config_a)

            self.assertEqual(1, first_a.stats.new_jobs)
            self.assertEqual(1, first_b.stats.new_jobs)
            self.assertEqual(0, second_a.stats.new_jobs)

    def test_brief_does_not_require_detail_fetch(self) -> None:
        vacancy = VacancyFull(
            id="vac-3",
            title="Junior Python Developer",
            company="Omega",
            place="Zurich",
            url="https://www.jobup.ch/en/jobs/detail/vac-3/",
            source="jobup.ch",
            raw={"workload": "100%"},
        )
        fake_client = FakeJobupChClient([vacancy])

        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(
                {
                    "client_id": "client_a",
                    "database_path": str(Path(tmpdir) / "client-a.sqlite"),
                    "mode": "search",
                    "terms": ["python developer"],
                    "locations": ["zurich"],
                    "output_format": "brief",
                    "skip_detail_schema": True,
                },
            )

            service = JobupChParserService(http_client=fake_client, runtime_root=Path(tmpdir))
            result = service.run(config)

            self.assertEqual(0, fake_client.enrich_calls)
            self.assertEqual("brief", result.effective_config.output_format)
            self.assertEqual(1, len(result.output_jobs))
            self.assertEqual("jobup.ch", result.output_jobs[0]["source"])


if __name__ == "__main__":
    unittest.main()

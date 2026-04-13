from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from swiss_jobs.core.models import ClientConfig, VacancyFull
from swiss_jobs.providers.jobscout24_ch.client import JobScout24ChHttpClient
from swiss_jobs.providers.jobscout24_ch.service import JobScout24ChParserService


class FakeJobScout24ChClient:
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


class JobScout24ChServiceTests(unittest.TestCase):
    def test_client_uses_term_route_for_search_url(self) -> None:
        client = JobScout24ChHttpClient()
        url = client._build_search_url(  # noqa: SLF001
            mode="search",
            term="software engineer",
            location="zurich",
        )
        self.assertEqual(
            "https://www.jobscout24.ch/en/jobs/software%20engineer/",
            url,
        )

    def test_client_state_is_isolated(self) -> None:
        vacancy = VacancyFull(
            id="shared-1",
            title="Python Developer",
            company="Acme",
            place="Zurich",
            url="https://www.jobscout24.ch/en/job/test/",
            source="jobscout24.ch",
        )
        fake_client = FakeJobScout24ChClient([vacancy])

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

            service = JobScout24ChParserService(http_client=fake_client, runtime_root=runtime_root)

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
            url="https://www.jobscout24.ch/en/job/test2/",
            source="jobscout24.ch",
        )
        fake_client = FakeJobScout24ChClient([vacancy])

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

            service = JobScout24ChParserService(http_client=fake_client, runtime_root=Path(tmpdir))
            result = service.run(config)

            self.assertEqual(0, fake_client.enrich_calls)
            self.assertEqual("brief", result.effective_config.output_format)
            self.assertEqual(1, len(result.output_jobs))


if __name__ == "__main__":
    unittest.main()

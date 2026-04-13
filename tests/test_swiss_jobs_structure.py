from __future__ import annotations

import unittest

from swiss_jobs.cli.parse import build_parser
from swiss_jobs.registry import get_cli_entrypoint, list_supported_sources
from swiss_jobs.providers.jobs_ch.service import JobsChParserService
from swiss_jobs.providers.jobscout24_ch.service import JobScout24ChParserService


class SwissJobsStructureTests(unittest.TestCase):
    def test_registry_lists_jobs_ch_source(self) -> None:
        self.assertIn("jobs_ch", list_supported_sources())
        self.assertIn("jobscout24_ch", list_supported_sources())

    def test_generic_parse_cli_accepts_source_flag(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["--source", "jobs_ch"])
        self.assertEqual("jobs_ch", parsed.source)
        parsed = parser.parse_args(["--source", "jobscout24_ch"])
        self.assertEqual("jobscout24_ch", parsed.source)

    def test_registry_returns_jobs_ch_cli(self) -> None:
        entrypoint = get_cli_entrypoint("jobs_ch")
        self.assertTrue(callable(entrypoint))

    def test_provider_service_imports(self) -> None:
        self.assertTrue(JobsChParserService)
        self.assertTrue(JobScout24ChParserService)


if __name__ == "__main__":
    unittest.main()

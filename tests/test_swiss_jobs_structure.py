from __future__ import annotations

import unittest

from swiss_jobs.cli.parse import build_parser
from swiss_jobs.registry import get_cli_entrypoint, list_supported_sources
from swiss_jobs.providers.jobs_ch.service import JobsChParserService


class SwissJobsStructureTests(unittest.TestCase):
    def test_registry_lists_jobs_ch_source(self) -> None:
        self.assertIn("jobs_ch", list_supported_sources())

    def test_generic_parse_cli_accepts_source_flag(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["--source", "jobs_ch"])
        self.assertEqual("jobs_ch", parsed.source)

    def test_registry_returns_jobs_ch_cli(self) -> None:
        entrypoint = get_cli_entrypoint("jobs_ch")
        self.assertTrue(callable(entrypoint))

    def test_provider_service_imports(self) -> None:
        self.assertTrue(JobsChParserService)


if __name__ == "__main__":
    unittest.main()

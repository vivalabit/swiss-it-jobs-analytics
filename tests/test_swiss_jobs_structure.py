from __future__ import annotations

import unittest
from pathlib import Path

from swiss_jobs.cli.parse import _build_source_args, _format_summary_line, build_parser
from swiss_jobs.registry import get_cli_entrypoint, get_source_info, list_supported_sources
from swiss_jobs.providers.jobs_ch.service import JobsChParserService
from swiss_jobs.providers.jobscout24_ch.service import JobScout24ChParserService
from swiss_jobs.providers.jobup_ch.service import JobupChParserService
from swiss_jobs.providers.linked_in.service import LinkedInParserService
from swiss_jobs.providers.swissdevjobs_ch.service import SwissDevJobsChParserService


class SwissJobsStructureTests(unittest.TestCase):
    def test_registry_lists_jobs_ch_source(self) -> None:
        self.assertIn("jobs_ch", list_supported_sources())
        self.assertIn("jobscout24_ch", list_supported_sources())
        self.assertIn("jobup_ch", list_supported_sources())
        self.assertIn("linked_in", list_supported_sources())
        self.assertIn("swissdevjobs_ch", list_supported_sources())

    def test_generic_parse_cli_accepts_source_flag(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["--source", "jobs_ch"])
        self.assertEqual("jobs_ch", parsed.source)
        self.assertFalse(parsed.all_sources)
        parsed = parser.parse_args(["--source", "jobscout24_ch"])
        self.assertEqual("jobscout24_ch", parsed.source)
        parsed = parser.parse_args(["--source", "jobup_ch"])
        self.assertEqual("jobup_ch", parsed.source)
        parsed = parser.parse_args(["--source", "linked_in"])
        self.assertEqual("linked_in", parsed.source)
        parsed = parser.parse_args(["--source", "swissdevjobs_ch"])
        self.assertEqual("swissdevjobs_ch", parsed.source)
        parsed = parser.parse_args(["--all-sources"])
        self.assertTrue(parsed.all_sources)
        self.assertIsNone(parsed.source)

    def test_registry_returns_jobs_ch_cli(self) -> None:
        entrypoint = get_cli_entrypoint("jobs_ch")
        self.assertTrue(callable(entrypoint))

    def test_registry_exposes_source_metadata(self) -> None:
        info = get_source_info("jobs_ch")
        self.assertEqual("jobs.ch", info.display_name)
        self.assertEqual("www.jobs.ch", info.domain)
        self.assertIn("portal", info.description.lower())
        self.assertTrue(Path(info.default_config_path).exists())

    def test_all_sources_uses_provider_default_config_when_missing(self) -> None:
        args, injected = _build_source_args("jobup_ch", ["--mode", "search"])
        self.assertTrue(injected)
        self.assertEqual("--config", args[0])
        self.assertEqual(get_source_info("jobup_ch").default_config_path, args[1])
        self.assertEqual(["--mode", "search"], args[2:])

    def test_all_sources_keeps_explicit_config(self) -> None:
        args, injected = _build_source_args("jobs_ch", ["--config", "/tmp/custom.json", "--mode", "search"])
        self.assertFalse(injected)
        self.assertEqual(["--config", "/tmp/custom.json", "--mode", "search"], args)

    def test_format_summary_line_contains_source_stats(self) -> None:
        line = _format_summary_line(
            "jobs_ch",
            {
                "success": True,
                "warnings_count": 1,
                "errors_count": 0,
                "stats": {
                    "total_fetched": 10,
                    "after_text_filters": 8,
                    "after_role_filters": 3,
                    "detail_attempted": 3,
                    "detail_enriched": 2,
                    "new_jobs": 1,
                },
            },
        )
        self.assertIn("jobs.ch", line)
        self.assertIn("fetched=10", line)
        self.assertIn("detail=2/3", line)
        self.assertIn("warnings=1", line)

    def test_provider_service_imports(self) -> None:
        self.assertTrue(JobsChParserService)
        self.assertTrue(JobScout24ChParserService)
        self.assertTrue(JobupChParserService)
        self.assertTrue(LinkedInParserService)
        self.assertTrue(SwissDevJobsChParserService)


if __name__ == "__main__":
    unittest.main()

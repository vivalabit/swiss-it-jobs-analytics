from __future__ import annotations

import argparse
import sys

from swiss_jobs.registry import get_cli_entrypoint, list_supported_sources


def build_parser(*, add_help: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dispatch parsing to a configured vacancy source provider.",
        add_help=add_help,
    )
    parser.add_argument(
        "--source",
        required=False,
        choices=list_supported_sources(),
        help="Provider source to run, for example jobs_ch.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true", dest="help_requested")
    args, remaining = parser.parse_known_args(argv)

    if args.help_requested and not args.source:
        build_parser().print_help()
        return 0
    if not args.source:
        parser.error("--source is required")

    provider_main = get_cli_entrypoint(args.source)
    if args.help_requested:
        remaining = ["--help", *remaining]
    return provider_main(remaining)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

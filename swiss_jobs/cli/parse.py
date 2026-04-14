from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading

from swiss_jobs.registry import get_cli_entrypoint, get_source_info, list_supported_sources

SUMMARY_MARKER = "__SWISS_JOBS_RUN_SUMMARY__"


def build_parser(*, add_help: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dispatch parsing to a configured vacancy source provider.",
        add_help=add_help,
    )
    source_group = parser.add_mutually_exclusive_group(required=False)
    source_group.add_argument(
        "--source",
        required=False,
        choices=list_supported_sources(),
        help="Provider source to run, for example jobs_ch.",
    )
    source_group.add_argument(
        "--all-sources",
        action="store_true",
        help="Run all supported vacancy sources in parallel.",
    )
    return parser


def _print_prefixed_stream(
    stream,  # noqa: ANN001
    *,
    source: str,
    prefix: str,
    target,
    summaries: dict[str, dict[str, object]],
    summary_lock: threading.Lock,
) -> None:
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            text = line.rstrip("\n")
            if text.startswith(f"{SUMMARY_MARKER} "):
                payload_text = text[len(SUMMARY_MARKER) + 1 :]
                try:
                    payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    print(f"{prefix} {text}", file=target)
                    continue
                with summary_lock:
                    summaries[source] = payload
                continue
            if text:
                print(f"{prefix} {text}", file=target)
    finally:
        stream.close()


def _build_source_args(source: str, remaining: list[str]) -> tuple[list[str], bool]:
    if "--config" in remaining:
        return list(remaining), False

    info = get_source_info(source)
    return ["--config", info.default_config_path, *remaining], True


def _format_summary_line(source: str, payload: dict[str, object]) -> str:
    info = get_source_info(source)
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    total_fetched = int(stats.get("total_fetched") or 0)
    after_text = int(stats.get("after_text_filters") or 0)
    after_role = int(stats.get("after_role_filters") or 0)
    detail_attempted = int(stats.get("detail_attempted") or 0)
    detail_enriched = int(stats.get("detail_enriched") or 0)
    new_jobs = int(stats.get("new_jobs") or 0)
    warnings_count = int(payload.get("warnings_count") or 0)
    errors_count = int(payload.get("errors_count") or 0)
    status = "ok" if bool(payload.get("success")) else "error"
    return (
        f"- {source} ({info.display_name}, {info.domain}): status={status}, "
        f"fetched={total_fetched}, text={after_text}, role={after_role}, "
        f"detail={detail_enriched}/{detail_attempted}, new={new_jobs}, "
        f"warnings={warnings_count}, errors={errors_count}"
    )


def _print_aggregate_summary(
    summaries: dict[str, dict[str, object]],
    process_statuses: dict[str, int],
) -> None:
    print("== Aggregate Summary ==", file=sys.stderr)
    total_fetched = 0
    total_after_text = 0
    total_after_role = 0
    total_detail_attempted = 0
    total_detail_enriched = 0
    total_new_jobs = 0
    total_warnings = 0
    total_errors = 0

    for source in list_supported_sources():
        payload = summaries.get(source)
        if payload is None:
            info = get_source_info(source)
            exit_code = process_statuses.get(source, 1)
            print(
                f"- {source} ({info.display_name}, {info.domain}): no summary available, exit_code={exit_code}",
                file=sys.stderr,
            )
            continue

        print(_format_summary_line(source, payload), file=sys.stderr)
        stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
        total_fetched += int(stats.get("total_fetched") or 0)
        total_after_text += int(stats.get("after_text_filters") or 0)
        total_after_role += int(stats.get("after_role_filters") or 0)
        total_detail_attempted += int(stats.get("detail_attempted") or 0)
        total_detail_enriched += int(stats.get("detail_enriched") or 0)
        total_new_jobs += int(stats.get("new_jobs") or 0)
        total_warnings += int(payload.get("warnings_count") or 0)
        total_errors += int(payload.get("errors_count") or 0)

    print(
        (
            f"Total: fetched={total_fetched}, text={total_after_text}, role={total_after_role}, "
            f"detail={total_detail_enriched}/{total_detail_attempted}, new={total_new_jobs}, "
            f"warnings={total_warnings}, errors={total_errors}"
        ),
        file=sys.stderr,
    )


def _run_all_sources(remaining: list[str]) -> int:
    processes: list[tuple[str, subprocess.Popen[str]]] = []
    reader_threads: list[threading.Thread] = []
    summaries: dict[str, dict[str, object]] = {}
    summary_lock = threading.Lock()

    for source in list_supported_sources():
        info = get_source_info(source)
        prefix = f"[{source} | {info.display_name} | {info.domain} | {info.description}]"
        source_args, injected_default_config = _build_source_args(source, remaining)
        if injected_default_config:
            print(
                f"{prefix} started with default config {info.default_config_path}",
                file=sys.stderr,
            )
        else:
            print(f"{prefix} started", file=sys.stderr)
        command = [
            sys.executable,
            "-m",
            "swiss_jobs.cli.parse",
            "--source",
            source,
            *source_args,
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        processes.append((source, process))
        assert process.stdout is not None
        assert process.stderr is not None
        reader_threads.append(
            threading.Thread(
                target=_print_prefixed_stream,
                kwargs={
                    "stream": process.stdout,
                    "source": source,
                    "prefix": prefix,
                    "target": sys.stdout,
                    "summaries": summaries,
                    "summary_lock": summary_lock,
                },
                daemon=True,
            )
        )
        reader_threads.append(
            threading.Thread(
                target=_print_prefixed_stream,
                kwargs={
                    "stream": process.stderr,
                    "source": source,
                    "prefix": prefix,
                    "target": sys.stderr,
                    "summaries": summaries,
                    "summary_lock": summary_lock,
                },
                daemon=True,
            )
        )

    for thread in reader_threads:
        thread.start()

    exit_code = 0
    process_statuses: dict[str, int] = {}
    for source, process in processes:
        return_code = process.wait()
        process_statuses[source] = return_code
        info = get_source_info(source)
        prefix = f"[{source} | {info.display_name} | {info.domain} | {info.description}]"
        status = "finished" if return_code == 0 else f"failed with exit code {return_code}"
        print(f"{prefix} {status}", file=sys.stderr)
        if return_code != 0:
            exit_code = 1

    for thread in reader_threads:
        thread.join()

    _print_aggregate_summary(summaries, process_statuses)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true", dest="help_requested")
    args, remaining = parser.parse_known_args(argv)

    if args.help_requested and not args.source and not args.all_sources:
        build_parser().print_help()
        return 0
    if args.all_sources:
        if args.help_requested:
            build_parser().print_help()
            return 0
        return _run_all_sources(remaining)
    if not args.source:
        parser.error("one of --source or --all-sources is required")

    provider_main = get_cli_entrypoint(args.source)
    if args.help_requested:
        remaining = ["--help", *remaining]
    return provider_main(remaining)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

from __future__ import annotations

import argparse
import base64
import html
import ipaddress
import io
import json
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse, urlunparse

import requests

from swiss_jobs.core.locations import location_search_terms, normalize_location_display
from swiss_jobs.registry import list_supported_sources

from .search_vacancies import DEFAULT_RUNTIME_DATABASES, _resolve_database_paths, _split_csv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_RUN_LOGS = 1000

TECH_TERM_TYPES = {
    "cloud_platform",
    "data_platform",
    "database",
    "framework_library",
    "methodology",
    "platform",
    "programming_language",
    "protocol_standard",
    "tool",
    "vendor",
}

FACET_TERM_TYPES = {
    "role_family_primary",
    "role_family",
    "seniority",
    "programming_language",
    "framework_library",
    "cloud_platform",
    "database",
    "tool",
    "methodology",
}

SEARCH_DEFAULT_PAGE_SIZE = 10
SEARCH_MAX_PAGE_SIZE = 100
PARSER_RUNS: dict[str, dict[str, Any]] = {}
PARSER_RUNS_LOCK = threading.Lock()
AI_ANALYSIS_RUNS: dict[str, dict[str, Any]] = {}
AI_ANALYSIS_RUNS_LOCK = threading.Lock()
PUBLIC_STATS_RUNS: dict[str, dict[str, Any]] = {}
PUBLIC_STATS_RUNS_LOCK = threading.Lock()
SOURCE_DATABASE_PATHS = {
    "jobs_ch": PROJECT_ROOT / "runtime" / "jobs_ch" / "main-config" / "jobs_ch.sqlite",
    "jobscout24_ch": PROJECT_ROOT / "runtime" / "jobscout24_ch" / "main-config" / "jobscout24_ch.sqlite",
    "jobup_ch": PROJECT_ROOT / "runtime" / "jobup_ch" / "main-config" / "jobup_ch.sqlite",
    "linked_in": PROJECT_ROOT / "runtime" / "linked_in" / "main-config" / "linked_in.sqlite",
    "swissdevjobs_ch": PROJECT_ROOT / "runtime" / "swissdevjobs_ch" / "main-config" / "swissdevjobs_ch.sqlite",
}

RESUME_MATCH_TERM_KEYS = (
    "programming_languages",
    "frameworks_libraries",
    "cloud_platforms",
    "databases",
    "tools",
    "methodologies",
    "methodology",
    "vendors",
    "platforms",
    "role_family_primary",
    "role_family",
    "remote_mode",
    "seniority_labels",
)

RESUME_MATCH_STOPWORDS = {
    "about",
    "also",
    "and",
    "are",
    "auf",
    "avec",
    "bei",
    "can",
    "das",
    "der",
    "die",
    "ein",
    "eine",
    "for",
    "from",
    "have",
    "ist",
    "mit",
    "not",
    "oder",
    "our",
    "per",
    "the",
    "und",
    "une",
    "von",
    "with",
    "you",
    "your",
    "zur",
    "zum",
    "experience",
    "knowledge",
    "looking",
    "need",
    "skills",
    "team",
    "required",
    "requirements",
    "role",
    "we",
    "will",
    "work",
    "working",
}
VACANCY_FETCH_MAX_BYTES = 2_000_000
VACANCY_FETCH_TIMEOUT = (5, 15)
VACANCY_FETCH_USER_AGENT = (
    "Mozilla/5.0 (compatible; SwissITJobsResumeMatcher/1.0; +https://localhost)"
)


@dataclass(frozen=True)
class LocalSearchConfig:
    database_paths: tuple[Path, ...]
    host: str
    port: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a local read-only web search UI for stored vacancy SQLite databases.",
    )
    parser.add_argument(
        "--database-path",
        action="append",
        default=[],
        help="SQLite database path. Can be repeated. Defaults to existing runtime/*/main-config/*.sqlite files.",
    )
    parser.add_argument("--host", help="Bind host. Defaults to 127.0.0.1, or 0.0.0.0 with --share-lan.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port. Defaults to 8765.")
    parser.add_argument("--open", action="store_true", help="Open the page in the default browser.")
    parser.add_argument(
        "--share-lan",
        action="store_true",
        help="Allow other devices on the same trusted local network to open the app.",
    )
    return parser


def _connect_readonly(database_path: Path) -> sqlite3.Connection:
    uri = database_path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _html_response(handler: BaseHTTPRequestHandler, content: str, status: int = 200) -> None:
    data = content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _text_response(handler: BaseHTTPRequestHandler, content: str, status: int = 200) -> None:
    data = content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _head_response(handler: BaseHTTPRequestHandler, content_type: str, status: int = 200) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.end_headers()


def _local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        host_name = socket.gethostname()
        for item in socket.getaddrinfo(host_name, None, socket.AF_INET, socket.SOCK_STREAM):
            address = item[4][0]
            if address and not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if address and not address.startswith("127."):
                addresses.add(address)
        finally:
            probe.close()
    except OSError:
        pass

    return sorted(addresses)


def _display_urls(host: str, port: int) -> list[str]:
    if host in {"0.0.0.0", "::", ""}:
        hosts = ["127.0.0.1", *_local_ipv4_addresses()]
    else:
        hosts = [host]
    return [f"http://{item}:{port}/" for item in dict.fromkeys(hosts)]


def _browser_open_url(host: str, port: int) -> str:
    if host in {"0.0.0.0", "::", ""}:
        return f"http://127.0.0.1:{port}/"
    return f"http://{host}:{port}/"


def _request_values(params: dict[str, list[str]], name: str) -> list[str]:
    return _split_csv_values(params.get(name, []))


def _request_int(params: dict[str, list[str]], name: str, default: int | None = None) -> int | None:
    raw = (params.get(name) or [""])[0].strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _request_date(params: dict[str, list[str]], name: str) -> str:
    raw = (params.get(name) or [""])[0].strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", raw)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    raise ValueError(f"{name} must use YYYY-MM-DD or dd.mm.yyyy format")


def _json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON request body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_positive_int(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError(f"expected integer value, got {text!r}") from exc
    if number < 0:
        raise ValueError(f"expected non-negative integer value, got {number}")
    return str(number)


def _clean_minimum_int(value: Any, *, minimum: int, name: str) -> str:
    text = _clean_positive_int(value)
    if not text:
        return ""
    number = int(text)
    if number < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return str(number)


def _clean_date(value: Any, name: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    raise ValueError(f"{name} must use YYYY-MM-DD or dd.mm.yyyy format")


def _parser_sources(payload: dict[str, Any]) -> list[str]:
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("sources must be a non-empty list")
    sources = [_clean_text(item) for item in raw_sources]
    sources = [source for source in sources if source]
    supported = set(list_supported_sources())
    unsupported = sorted(source for source in sources if source not in supported)
    if unsupported:
        raise ValueError(f"unsupported source(s): {', '.join(unsupported)}")
    if not sources:
        raise ValueError("at least one parser source must be selected")
    return sorted(set(sources))


def _parser_cli_args(payload: dict[str, Any]) -> list[str]:
    args: list[str] = []
    mode = _clean_text(payload.get("mode"))
    if mode:
        if mode not in {"new", "search"}:
            raise ValueError("mode must be new or search")
        args.extend(["--mode", mode])
    for payload_key, cli_key in (
        ("canton", "--canton"),
        ("term", "--term"),
        ("location", "--location"),
    ):
        value = _clean_text(payload.get(payload_key))
        if value:
            args.extend([cli_key, value])
    for payload_key, cli_key in (
        ("max_pages", "--max-pages"),
        ("detail_limit", "--detail-limit"),
    ):
        value = _clean_positive_int(payload.get(payload_key))
        if value:
            args.extend([cli_key, value])
    return args


def _parser_command(source: str, cli_args: list[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "swiss_jobs.cli.parse",
        "--source",
        source,
        *cli_args,
    ]


def _append_parser_log(
    run_id: str,
    message: str,
    *,
    source: str = "",
    stream: str = "system",
    level: str = "info",
) -> None:
    if not message:
        return
    with PARSER_RUNS_LOCK:
        run = PARSER_RUNS.get(run_id)
        if not run:
            return
        run["next_seq"] += 1
        entry = {
            "seq": run["next_seq"],
            "time": time.strftime("%H:%M:%S"),
            "source": source,
            "stream": stream,
            "level": level,
            "message": message,
        }
        logs = run["logs"]
        logs.append(entry)
        if len(logs) > MAX_RUN_LOGS:
            del logs[: len(logs) - MAX_RUN_LOGS]


def _read_process_stream(run_id: str, source: str, stream_name: str, stream: Any) -> None:
    try:
        for line in iter(stream.readline, ""):
            text = line.rstrip("\n")
            if text:
                level = "error" if stream_name == "stderr" and "[error]" in text.lower() else "info"
                _append_parser_log(run_id, text, source=source, stream=stream_name, level=level)
    finally:
        stream.close()


def _run_parser_processes(run_id: str, sources: list[str], cli_args: list[str]) -> None:
    exit_code = 0
    try:
        with PARSER_RUNS_LOCK:
            if run_id in PARSER_RUNS:
                PARSER_RUNS[run_id]["status"] = "running"
        _append_parser_log(run_id, f"Parser run started for {', '.join(sources)}.")
        for source in sources:
            command = _parser_command(source, cli_args)
            _append_parser_log(run_id, "$ " + " ".join(command), source=source)
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            assert process.stderr is not None
            stdout_thread = threading.Thread(
                target=_read_process_stream,
                args=(run_id, source, "stdout", process.stdout),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_read_process_stream,
                args=(run_id, source, "stderr", process.stderr),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()
            return_code = process.wait()
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            if return_code == 0:
                _append_parser_log(run_id, f"{source} finished successfully.", source=source, level="success")
            else:
                exit_code = 1
                _append_parser_log(
                    run_id,
                    f"{source} failed with exit code {return_code}.",
                    source=source,
                    level="error",
                )
        final_status = "completed" if exit_code == 0 else "failed"
        _append_parser_log(run_id, f"Parser run {final_status}.", level="success" if exit_code == 0 else "error")
        with PARSER_RUNS_LOCK:
            if run_id in PARSER_RUNS:
                PARSER_RUNS[run_id]["status"] = final_status
                PARSER_RUNS[run_id]["return_code"] = exit_code
                PARSER_RUNS[run_id]["finished_at"] = time.time()
    except Exception as exc:  # noqa: BLE001
        _append_parser_log(run_id, f"Parser run crashed: {exc}", level="error")
        with PARSER_RUNS_LOCK:
            if run_id in PARSER_RUNS:
                PARSER_RUNS[run_id]["status"] = "failed"
                PARSER_RUNS[run_id]["return_code"] = 1
                PARSER_RUNS[run_id]["finished_at"] = time.time()


def start_parser_run(payload: dict[str, Any]) -> dict[str, Any]:
    sources = _parser_sources(payload)
    cli_args = _parser_cli_args(payload)
    run_id = uuid.uuid4().hex
    with PARSER_RUNS_LOCK:
        PARSER_RUNS[run_id] = {
            "id": run_id,
            "status": "queued",
            "sources": sources,
            "args": cli_args,
            "logs": [],
            "next_seq": 0,
            "return_code": None,
            "started_at": time.time(),
            "finished_at": None,
        }
    thread = threading.Thread(target=_run_parser_processes, args=(run_id, sources, cli_args), daemon=True)
    thread.start()
    return get_parser_run(run_id, after_seq=0)


def get_parser_run(run_id: str, *, after_seq: int = 0) -> dict[str, Any]:
    with PARSER_RUNS_LOCK:
        run = PARSER_RUNS.get(run_id)
        if run is None:
            raise ValueError(f"unknown parser run: {run_id}")
        logs = [entry for entry in run["logs"] if int(entry["seq"]) > after_seq]
        return {
            "id": run["id"],
            "status": run["status"],
            "sources": run["sources"],
            "args": run["args"],
            "logs": logs,
            "last_seq": run["next_seq"],
            "return_code": run["return_code"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
        }


def _analysis_sources(payload: dict[str, Any]) -> list[str]:
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("sources must be a non-empty list")
    sources = [_clean_text(item) for item in raw_sources]
    sources = [source for source in sources if source]
    supported = set(list_supported_sources())
    unsupported = sorted(source for source in sources if source not in supported)
    if unsupported:
        raise ValueError(f"unsupported source(s): {', '.join(unsupported)}")
    if not sources:
        raise ValueError("at least one AI analysis source must be selected")
    return sorted(set(sources))


def _analysis_cli_args(payload: dict[str, Any]) -> list[str]:
    args: list[str] = []
    model = _clean_text(payload.get("model")) or "gpt-5-nano"
    args.extend(["--model", model])

    for payload_key, cli_key in (
        ("first_seen_from", "--first-seen-from"),
        ("first_seen_to", "--first-seen-to"),
    ):
        value = _clean_date(payload.get(payload_key), payload_key)
        if value:
            args.extend([cli_key, value])

    limit = _clean_positive_int(payload.get("limit"))
    scope = _clean_text(payload.get("scope")) or "new vacancies only"
    if scope == "all selected vacancies":
        args.append("--include-analyzed")
        if limit:
            args.extend(["--limit", limit])
        else:
            args.append("--all")
    else:
        if limit:
            args.extend(["--limit", limit])
    return args


def _analysis_command(source: str, cli_args: list[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "swiss_jobs.cli.analyze_vacancies_llm",
        "--source",
        source,
        *cli_args,
    ]


def _append_ai_analysis_log(
    run_id: str,
    message: str,
    *,
    source: str = "",
    stream: str = "system",
    level: str = "info",
) -> None:
    if not message:
        return
    with AI_ANALYSIS_RUNS_LOCK:
        run = AI_ANALYSIS_RUNS.get(run_id)
        if not run:
            return
        run["next_seq"] += 1
        entry = {
            "seq": run["next_seq"],
            "time": time.strftime("%H:%M:%S"),
            "source": source,
            "stream": stream,
            "level": level,
            "message": message,
        }
        logs = run["logs"]
        logs.append(entry)
        if len(logs) > MAX_RUN_LOGS:
            del logs[: len(logs) - MAX_RUN_LOGS]


def _read_ai_analysis_stream(run_id: str, source: str, stream_name: str, stream: Any) -> None:
    try:
        for line in iter(stream.readline, ""):
            text = line.rstrip("\n")
            if text:
                lowered = text.lower()
                level = "error" if stream_name == "stderr" and ("error" in lowered or "failed" in lowered) else "info"
                _append_ai_analysis_log(run_id, text, source=source, stream=stream_name, level=level)
    finally:
        stream.close()


def _run_ai_analysis_processes(run_id: str, sources: list[str], cli_args: list[str]) -> None:
    exit_code = 0
    try:
        with AI_ANALYSIS_RUNS_LOCK:
            if run_id in AI_ANALYSIS_RUNS:
                AI_ANALYSIS_RUNS[run_id]["status"] = "running"
        _append_ai_analysis_log(run_id, f"AI analysis run started for {', '.join(sources)}.")
        for source in sources:
            command = _analysis_command(source, cli_args)
            _append_ai_analysis_log(run_id, "$ " + " ".join(command), source=source)
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            assert process.stderr is not None
            stdout_thread = threading.Thread(
                target=_read_ai_analysis_stream,
                args=(run_id, source, "stdout", process.stdout),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_read_ai_analysis_stream,
                args=(run_id, source, "stderr", process.stderr),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()
            return_code = process.wait()
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            if return_code == 0:
                _append_ai_analysis_log(run_id, f"{source} AI analysis finished successfully.", source=source, level="success")
            else:
                exit_code = 1
                _append_ai_analysis_log(
                    run_id,
                    f"{source} AI analysis failed with exit code {return_code}.",
                    source=source,
                    level="error",
                )
        final_status = "completed" if exit_code == 0 else "failed"
        _append_ai_analysis_log(run_id, f"AI analysis run {final_status}.", level="success" if exit_code == 0 else "error")
        with AI_ANALYSIS_RUNS_LOCK:
            if run_id in AI_ANALYSIS_RUNS:
                AI_ANALYSIS_RUNS[run_id]["status"] = final_status
                AI_ANALYSIS_RUNS[run_id]["return_code"] = exit_code
                AI_ANALYSIS_RUNS[run_id]["finished_at"] = time.time()
    except Exception as exc:  # noqa: BLE001
        _append_ai_analysis_log(run_id, f"AI analysis run crashed: {exc}", level="error")
        with AI_ANALYSIS_RUNS_LOCK:
            if run_id in AI_ANALYSIS_RUNS:
                AI_ANALYSIS_RUNS[run_id]["status"] = "failed"
                AI_ANALYSIS_RUNS[run_id]["return_code"] = 1
                AI_ANALYSIS_RUNS[run_id]["finished_at"] = time.time()


def start_ai_analysis_run(payload: dict[str, Any]) -> dict[str, Any]:
    sources = _analysis_sources(payload)
    cli_args = _analysis_cli_args(payload)
    run_id = uuid.uuid4().hex
    with AI_ANALYSIS_RUNS_LOCK:
        AI_ANALYSIS_RUNS[run_id] = {
            "id": run_id,
            "status": "queued",
            "sources": sources,
            "args": cli_args,
            "logs": [],
            "next_seq": 0,
            "return_code": None,
            "started_at": time.time(),
            "finished_at": None,
        }
    thread = threading.Thread(target=_run_ai_analysis_processes, args=(run_id, sources, cli_args), daemon=True)
    thread.start()
    return get_ai_analysis_run(run_id, after_seq=0)


def get_ai_analysis_run(run_id: str, *, after_seq: int = 0) -> dict[str, Any]:
    with AI_ANALYSIS_RUNS_LOCK:
        run = AI_ANALYSIS_RUNS.get(run_id)
        if run is None:
            raise ValueError(f"unknown AI analysis run: {run_id}")
        logs = [entry for entry in run["logs"] if int(entry["seq"]) > after_seq]
        return {
            "id": run["id"],
            "status": run["status"],
            "sources": run["sources"],
            "args": run["args"],
            "logs": logs,
            "last_seq": run["next_seq"],
            "return_code": run["return_code"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
        }


def _public_stats_sources(payload: dict[str, Any]) -> list[str]:
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("sources must be a non-empty list")
    sources = [_clean_text(item) for item in raw_sources]
    sources = [source for source in sources if source]
    supported = set(SOURCE_DATABASE_PATHS)
    unsupported = sorted(source for source in sources if source not in supported)
    if unsupported:
        raise ValueError(f"unsupported source(s): {', '.join(unsupported)}")
    if not sources:
        raise ValueError("at least one public stats source must be selected")
    return sorted(set(sources))


def _resolve_workspace_path(value: Any, default: str) -> Path:
    text = _clean_text(value) or default
    path = Path(text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _public_stats_options(payload: dict[str, Any]) -> dict[str, str | bool]:
    return {
        "output_dir": _clean_text(payload.get("output_dir")) or "public_stats",
        "site_dir": _clean_text(payload.get("site_dir")) or "site/public",
        "snapshot_date": _clean_date(payload.get("snapshot_date"), "snapshot_date"),
        "salary_group_minimum": _clean_minimum_int(
            _clean_text(payload.get("salary_group_minimum")) or "10",
            minimum=1,
            name="salary_group_minimum",
        ),
        "sync_site": bool(payload.get("sync_site", True)),
    }


def _append_public_stats_log(
    run_id: str,
    message: str,
    *,
    stage: str = "",
    stream: str = "system",
    level: str = "info",
) -> None:
    if not message:
        return
    with PUBLIC_STATS_RUNS_LOCK:
        run = PUBLIC_STATS_RUNS.get(run_id)
        if not run:
            return
        run["next_seq"] += 1
        entry = {
            "seq": run["next_seq"],
            "time": time.strftime("%H:%M:%S"),
            "source": stage,
            "stream": stream,
            "level": level,
            "message": message,
        }
        logs = run["logs"]
        logs.append(entry)
        if len(logs) > MAX_RUN_LOGS:
            del logs[: len(logs) - MAX_RUN_LOGS]


def _read_public_stats_stream(run_id: str, stage: str, stream_name: str, stream: Any) -> None:
    try:
        for line in iter(stream.readline, ""):
            text = line.rstrip("\n")
            if text:
                lowered = text.lower()
                level = "error" if stream_name == "stderr" and ("error" in lowered or "failed" in lowered) else "info"
                _append_public_stats_log(run_id, text, stage=stage, stream=stream_name, level=level)
    finally:
        stream.close()


def _run_public_stats_command(run_id: str, stage: str, command: list[str]) -> int:
    _append_public_stats_log(run_id, "$ " + " ".join(command), stage=stage)
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_thread = threading.Thread(
        target=_read_public_stats_stream,
        args=(run_id, stage, "stdout", process.stdout),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_public_stats_stream,
        args=(run_id, stage, "stderr", process.stderr),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    return_code = process.wait()
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    return return_code


def _public_stats_command_plan(payload: dict[str, Any]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    sources = _public_stats_sources(payload)
    options = _public_stats_options(payload)
    dataset_paths = [str(SOURCE_DATABASE_PATHS[source]) for source in sources]
    analytics_dir = PROJECT_ROOT / "analytics_output"
    output_root = _resolve_workspace_path(options["output_dir"], "public_stats")
    data_dir = output_root / "data"
    csv_dir = output_root / "csv"
    site_dir = _resolve_workspace_path(options["site_dir"], "site/public")

    analytics_command = [
        sys.executable,
        "scripts/export_analytics.py",
        *dataset_paths,
        "--output-dir",
        str(analytics_dir),
    ]
    if options["salary_group_minimum"]:
        analytics_command.extend(
            ["--salary-group-minimum", str(options["salary_group_minimum"])]
        )

    snapshot_command = [
        sys.executable,
        "scripts/build_public_stats.py",
        "--csv-dir",
        str(analytics_dir),
        "--output-dir",
        str(data_dir),
        "--copy-csv-dir",
        str(csv_dir),
    ]
    if options["snapshot_date"]:
        snapshot_command.extend(["--snapshot-date", str(options["snapshot_date"])])

    commands = [
        ("analytics", analytics_command),
        ("snapshot", snapshot_command),
    ]
    if options["sync_site"]:
        commands.append(
            (
                "site-sync",
                [
                    "node",
                    "site/scripts/sync-public-data.mjs",
                    "--source-public-dir",
                    str(output_root),
                    "--target-public-dir",
                    str(site_dir),
                ],
            )
        )
    return sources, commands


def _run_public_stats_process(run_id: str, payload: dict[str, Any]) -> None:
    try:
        sources, commands = _public_stats_command_plan(payload)
        with PUBLIC_STATS_RUNS_LOCK:
            if run_id in PUBLIC_STATS_RUNS:
                PUBLIC_STATS_RUNS[run_id]["status"] = "running"
        _append_public_stats_log(run_id, f"Public stats build started for {', '.join(sources)}.")

        exit_code = 0
        for stage, command in commands:
            _append_public_stats_log(run_id, f"Starting {stage} stage.", stage=stage)
            return_code = _run_public_stats_command(run_id, stage, command)
            if return_code == 0:
                _append_public_stats_log(run_id, f"{stage} stage completed.", stage=stage, level="success")
                continue
            exit_code = 1
            _append_public_stats_log(run_id, f"{stage} stage failed with exit code {return_code}.", stage=stage, level="error")
            break

        final_status = "completed" if exit_code == 0 else "failed"
        _append_public_stats_log(run_id, f"Public stats build {final_status}.", level="success" if exit_code == 0 else "error")
        with PUBLIC_STATS_RUNS_LOCK:
            if run_id in PUBLIC_STATS_RUNS:
                PUBLIC_STATS_RUNS[run_id]["status"] = final_status
                PUBLIC_STATS_RUNS[run_id]["return_code"] = exit_code
                PUBLIC_STATS_RUNS[run_id]["finished_at"] = time.time()
    except Exception as exc:  # noqa: BLE001
        _append_public_stats_log(run_id, f"Public stats build crashed: {exc}", level="error")
        with PUBLIC_STATS_RUNS_LOCK:
            if run_id in PUBLIC_STATS_RUNS:
                PUBLIC_STATS_RUNS[run_id]["status"] = "failed"
                PUBLIC_STATS_RUNS[run_id]["return_code"] = 1
                PUBLIC_STATS_RUNS[run_id]["finished_at"] = time.time()


def start_public_stats_run(payload: dict[str, Any]) -> dict[str, Any]:
    sources = _public_stats_sources(payload)
    options = _public_stats_options(payload)
    run_id = uuid.uuid4().hex
    with PUBLIC_STATS_RUNS_LOCK:
        PUBLIC_STATS_RUNS[run_id] = {
            "id": run_id,
            "status": "queued",
            "sources": sources,
            "args": options,
            "logs": [],
            "next_seq": 0,
            "return_code": None,
            "started_at": time.time(),
            "finished_at": None,
        }
    thread = threading.Thread(target=_run_public_stats_process, args=(run_id, payload), daemon=True)
    thread.start()
    return get_public_stats_run(run_id, after_seq=0)


def get_public_stats_run(run_id: str, *, after_seq: int = 0) -> dict[str, Any]:
    with PUBLIC_STATS_RUNS_LOCK:
        run = PUBLIC_STATS_RUNS.get(run_id)
        if run is None:
            raise ValueError(f"unknown public stats run: {run_id}")
        logs = [entry for entry in run["logs"] if int(entry["seq"]) > after_seq]
        return {
            "id": run["id"],
            "status": run["status"],
            "sources": run["sources"],
            "args": run["args"],
            "logs": logs,
            "last_seq": run["next_seq"],
            "return_code": run["return_code"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
        }


def _date_filter_expression(field_name: str) -> tuple[str, bool]:
    if field_name == "published":
        return "substr(COALESCE(v.publication_date, v.initial_publication_date, ''), 1, 10)", True
    if field_name == "first_seen":
        return "substr(v.first_seen_at, 1, 10)", False
    return "substr(v.last_seen_at, 1, 10)", False


def _search_words(value: str) -> list[str]:
    return [word.lower() for word in re.findall(r"[\w.+#-]+", value, flags=re.UNICODE) if word.strip()]


def _load_json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload if item is not None and str(item).strip()]


def _database_label(database_path: Path) -> str:
    parts = database_path.parts
    if len(parts) >= 3 and parts[-2] == "main-config":
        return parts[-3]
    return database_path.stem


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        clean = value.strip()
        return [clean] if clean else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_listify(item))
        return result
    return [str(value)]


def _format_salary(row: sqlite3.Row) -> str:
    salary_text = row["salary_text"]
    if isinstance(salary_text, str) and salary_text.strip():
        return salary_text.strip()

    minimum = row["salary_min"]
    maximum = row["salary_max"]
    currency = str(row["salary_currency"] or "").strip()
    unit = str(row["salary_unit"] or "").strip().lower()
    prefix = f"{currency} " if currency else ""
    suffix = f" / {unit}" if unit else ""

    if isinstance(minimum, int) and isinstance(maximum, int):
        if minimum == maximum:
            return f"{prefix}{minimum}{suffix}".strip()
        return f"{prefix}{minimum}-{maximum}{suffix}".strip()
    if isinstance(minimum, int):
        return f"{prefix}{minimum}{suffix}".strip()
    if isinstance(maximum, int):
        return f"{prefix}{maximum}{suffix}".strip()
    return ""


def _normalized_url_candidates(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []

    candidates = {text, text.rstrip("/")}
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            path=parsed.path.rstrip("/") or parsed.path,
            fragment="",
        )
        candidates.add(urlunparse(normalized))
        candidates.add(urlunparse(normalized._replace(query="")))
    return sorted(candidate for candidate in candidates if candidate)


def _resume_text_terms(text: str, *, limit: int = 18) -> list[str]:
    counts: dict[str, int] = {}
    for raw_word in re.findall(r"[\w.+#-]+", text, flags=re.UNICODE):
        word = raw_word.strip("._-").lower()
        if len(word) < 2 or word.isdigit() or word in RESUME_MATCH_STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [
        term
        for term, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _resume_terms_from_analytics(analytics: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in RESUME_MATCH_TERM_KEYS:
        terms.extend(_listify(analytics.get(key)))
    return terms


def _dedupe_terms(values: Iterable[Any], *, limit: int = 24) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        term = str(value or "").strip()
        if not term:
            continue
        normalized = term.lower()
        if normalized in seen or normalized in RESUME_MATCH_STOPWORDS:
            continue
        seen.add(normalized)
        terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def _resume_vacancy_from_row(database_path: Path, row: sqlite3.Row) -> dict[str, Any]:
    analytics = _load_json_object(row["analytics_json"])
    return {
        "database": str(database_path),
        "id": row["vacancy_id"],
        "source": row["source"] or "",
        "title": row["title"] or "",
        "company": row["company"] or "",
        "location": normalize_location_display(row["place"]) or row["place"] or "",
        "url": row["url"] or "",
        "description_text": str(row["description_text"] or "").strip(),
        "analytics": analytics,
    }


def _find_resume_vacancy(database_paths: Iterable[Path], vacancy_url: str) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    candidates = _normalized_url_candidates(vacancy_url)
    if not candidates:
        return None, []

    placeholders = ", ".join("?" for _ in candidates)
    query = f"""
        SELECT
            v.vacancy_id,
            v.source,
            v.title,
            v.company,
            v.place,
            v.url,
            v.description_text,
            v.analytics_json
        FROM vacancies v
        WHERE v.url IN ({placeholders})
           OR rtrim(v.url, '/') IN ({placeholders})
        ORDER BY v.last_seen_at DESC, v.vacancy_id ASC
        LIMIT 1
    """
    values = [*candidates, *[candidate.rstrip("/") for candidate in candidates]]
    database_errors: list[dict[str, str]] = []

    for database_path in database_paths:
        try:
            connection = _connect_readonly(database_path)
            try:
                row = connection.execute(query, values).fetchone()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            database_errors.append({"database": str(database_path), "error": str(exc)})
            continue
        if row:
            return _resume_vacancy_from_row(database_path, row), database_errors
    return None, database_errors


class _VacancyHtmlTextParser(HTMLParser):
    _skip_tags = {"script", "style", "noscript", "svg", "canvas", "template"}
    _block_tags = {
        "article",
        "br",
        "dd",
        "div",
        "dt",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "p",
        "section",
        "td",
        "th",
        "tr",
        "ul",
        "ol",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self.meta_title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._skip_tags:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            data = {str(key).lower(): str(value or "").strip() for key, value in attrs}
            key = data.get("property") or data.get("name")
            if key in {"og:title", "twitter:title", "title"} and data.get("content"):
                self.meta_title = data["content"]
        if tag in self._block_tags:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._skip_tags and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag in self._block_tags:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
        self._parts.append(text)

    @property
    def title(self) -> str:
        return self.meta_title or " ".join(self._title_parts).strip()

    @property
    def text(self) -> str:
        raw = " ".join(self._parts)
        raw = re.sub(r"\s*\n\s*", "\n", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        lines = []
        seen: set[str] = set()
        for line in raw.splitlines():
            clean = line.strip()
            if len(clean) < 2:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(clean)
        return "\n".join(lines)


def _is_disallowed_fetch_host(hostname: str) -> bool:
    clean = hostname.strip().strip("[]").lower()
    if clean in {"localhost", "0.0.0.0"} or clean.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(clean)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local or address.is_multicast


def _extract_external_vacancy_text(content: bytes, content_type: str, encoding: str = "") -> tuple[str, str]:
    charset = encoding or "utf-8"
    html_text = content.decode(charset, errors="replace")
    if "html" not in content_type.lower():
        text = re.sub(r"\r\n?", "\n", html_text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return "", text

    parser = _VacancyHtmlTextParser()
    parser.feed(html_text)
    parser.close()
    return parser.title.strip(), parser.text.strip()


def fetch_external_vacancy(vacancy_url: str) -> dict[str, Any] | None:
    text = _clean_text(vacancy_url)
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("vacancy URL must be an http or https URL")
    if parsed.hostname and _is_disallowed_fetch_host(parsed.hostname):
        raise ValueError("refusing to fetch private or local network vacancy URL")

    try:
        response = requests.get(
            text,
            headers={
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
                "User-Agent": VACANCY_FETCH_USER_AGENT,
            },
            timeout=VACANCY_FETCH_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"could not fetch vacancy URL: {exc}") from exc

    try:
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=32768):
            if not chunk:
                continue
            size += len(chunk)
            if size > VACANCY_FETCH_MAX_BYTES:
                raise ValueError("vacancy page is too large to read automatically")
            chunks.append(chunk)
    finally:
        response.close()

    content_type = response.headers.get("content-type", "")
    title, description = _extract_external_vacancy_text(
        b"".join(chunks),
        content_type,
        response.encoding or "",
    )
    if len(description) < 80:
        raise ValueError("could not extract enough vacancy text from URL; paste the vacancy description manually")

    return {
        "database": "",
        "id": "",
        "source": "web",
        "title": title,
        "company": "",
        "location": "",
        "url": response.url,
        "description_text": description[:12000],
        "analytics": {},
        "fetched_from_url": True,
    }


def _decode_pdf_base64(value: Any) -> bytes:
    text = _clean_text(value)
    if not text:
        return b""
    if "," in text and text.lower().startswith("data:"):
        text = text.split(",", 1)[1]
    try:
        return base64.b64decode(text, validate=True)
    except ValueError as exc:
        raise ValueError("resume PDF payload is not valid base64") from exc


def extract_resume_pdf_text(payload: dict[str, Any]) -> str:
    pdf_bytes = _decode_pdf_base64(payload.get("resume_pdf_base64"))
    if not pdf_bytes:
        return ""
    if len(pdf_bytes) > 12 * 1024 * 1024:
        raise ValueError("resume PDF is too large; use a file up to 12 MB")

    try:
        import pdfplumber
    except ImportError as exc:
        raise ValueError("PDF resume upload requires pdfplumber. Install project dependencies first.") from exc

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [(page.extract_text() or "").strip() for page in pdf.pages]
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not read resume PDF: {exc}") from exc

    text = "\n\n".join(page for page in pages if page)
    if not text:
        raise ValueError("could not extract text from resume PDF")
    return text


def build_resume_pdf_bytes(text: str, *, title: str = "Tailored Resume Draft") -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise ValueError("PDF resume export requires reportlab. Install project dependencies first.") from exc

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ResumeTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#121722"),
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "ResumeHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#d71920"),
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "ResumeBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#17202a"),
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "ResumeBullet",
        parent=body_style,
        leftIndent=10,
        firstLineIndent=-6,
    )

    story: list[Any] = [Paragraph(html.escape(title), title_style)]
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 5))
            continue
        style = body_style
        rendered = html.escape(line)
        if len(line) <= 72 and not line.endswith((".", ",", ";")) and not line.startswith("- "):
            style = heading_style
        elif line.startswith("- "):
            style = bullet_style
            rendered = "- " + html.escape(line[2:])
        story.append(Paragraph(rendered, style))

    document.build(story)
    return buffer.getvalue()


def _resume_pdf_filename(vacancy_title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", vacancy_title.lower()).strip("-")
    return f"tailored-resume-{slug or 'draft'}.pdf"


def build_resume_match(database_paths: Iterable[Path], payload: dict[str, Any]) -> dict[str, Any]:
    vacancy_url = _clean_text(payload.get("vacancy_url"))
    resume_pdf_text = extract_resume_pdf_text(payload)
    resume_text = resume_pdf_text or _clean_text(payload.get("resume_text"))
    pasted_description = _clean_text(payload.get("job_description"))
    vacancy, database_errors = _find_resume_vacancy(database_paths, vacancy_url)
    fetched_vacancy = None
    vacancy_fetch_error = ""
    if not vacancy and vacancy_url:
        try:
            fetched_vacancy = fetch_external_vacancy(vacancy_url)
        except ValueError as exc:
            if not pasted_description:
                raise
            vacancy_fetch_error = str(exc)

    if not vacancy and not fetched_vacancy and not pasted_description:
        raise ValueError("vacancy URL was not found in local databases and could not be fetched; paste the vacancy description too")

    vacancy_source = vacancy or fetched_vacancy or {}
    vacancy_title = _clean_text(payload.get("target_title")) or vacancy_source.get("title", "")
    company = vacancy_source.get("company", "")
    vacancy_text = vacancy_source.get("description_text") or pasted_description
    analytics = vacancy_source.get("analytics", {})
    terms = _dedupe_terms(
        [
            *_resume_terms_from_analytics(analytics),
            *_resume_text_terms(f"{vacancy_title} {vacancy_text}", limit=36),
        ],
        limit=24,
    )

    resume_lower = resume_text.lower()
    matched_terms = [term for term in terms if term.lower() in resume_lower]
    missing_terms = [term for term in terms if term.lower() not in resume_lower]
    score = round((len(matched_terms) / len(terms)) * 100) if terms else 0

    resume_lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    evidence_lines = [
        line
        for line in resume_lines
        if any(term.lower() in line.lower() for term in matched_terms)
    ][:6]

    recommendations = []
    if matched_terms:
        recommendations.append(
            "Move the strongest matching evidence near the top: "
            + ", ".join(matched_terms[:6])
            + "."
        )
    if missing_terms:
        recommendations.append(
            "Add truthful project or impact evidence for: "
            + ", ".join(missing_terms[:8])
            + "."
        )
    recommendations.append("Keep every added keyword backed by real experience, metrics, or project context.")

    target_line = vacancy_title or "Target role"
    company_line = f" at {company}" if company else ""
    source_line = f"Source: {vacancy_url}" if vacancy_url else "Source: pasted vacancy description"
    summary_terms = ", ".join((matched_terms or terms)[:6]) or "the role requirements"
    missing_line = ", ".join(missing_terms[:8]) if missing_terms else "No obvious missing priority terms."
    evidence_block = "\n".join(f"- {line}" for line in evidence_lines) or "- Add 3-5 resume bullets that prove the strongest requirements."
    original_block = resume_text or "[Paste your current resume here before generating the final version.]"
    tailored_resume = f"""Targeted Resume Draft
{target_line}{company_line}
{source_line}

Professional Summary
Candidate profile aligned with {target_line}, emphasizing {summary_terms}. Replace this sentence with a concise 2-3 line summary using only claims you can defend.

Selected Fit Highlights
{evidence_block}

Keywords To Weave In Truthfully
{missing_line}

Resume Draft
{original_block}
"""
    pdf_bytes = build_resume_pdf_bytes(tailored_resume, title=target_line)

    return {
        "vacancy_found": bool(vacancy),
        "vacancy_fetched": bool(fetched_vacancy),
        "vacancy_fetch_error": vacancy_fetch_error,
        "vacancy": vacancy_source or None,
        "score": score,
        "required_keywords": terms,
        "matched_keywords": matched_terms,
        "missing_keywords": missing_terms,
        "recommendations": recommendations,
        "tailored_resume": tailored_resume,
        "tailored_resume_pdf": {
            "filename": _resume_pdf_filename(target_line),
            "mime_type": "application/pdf",
            "base64": base64.b64encode(pdf_bytes).decode("ascii"),
        },
        "resume_pdf_text_extracted": bool(resume_pdf_text),
        "database_errors": database_errors,
    }


def _select_effective_seniority(title: Any, labels: Iterable[Any]) -> str:
    title_text = f" {str(title or '').lower()} "
    title_patterns = (
        ("manager", r"\b(?:head|manager|teamleiter|leiter|responsable)\b"),
        ("senior", r"\b(?:lead|senior|staff|principal|architect|expert)\b"),
        ("intern", r"\b(?:intern|internship|praktikum|praktikant|stagiaire)\b"),
        ("junior", r"\b(?:junior|trainee|graduate|entry[-\s]?level)\b"),
        ("mid", r"\b(?:mid|middle)\b"),
    )
    for label, pattern in title_patterns:
        if re.search(pattern, title_text):
            return label

    normalized_labels = {
        str(label).strip().lower()
        for label in labels
        if label is not None and str(label).strip()
    }
    for label in ("manager", "senior", "mid", "junior", "intern"):
        if label in normalized_labels:
            return label
    return ""


def _row_score(row: sqlite3.Row, words: list[str]) -> int:
    title = str(row["title"] or "").lower()
    company = str(row["company"] or "").lower()
    place = str(row["place"] or "").lower()
    description = str(row["description_text"] or "").lower()
    score = 0
    for word in words:
        if word in title:
            score += 20
        if word in company:
            score += 8
        if word in place:
            score += 6
        if word in description:
            score += 2
    if row["salary_min"] is not None or row["salary_max"] is not None:
        score += 3
    return score


def _build_where(params: dict[str, list[str]]) -> tuple[str, list[Any], list[str]]:
    clauses: list[str] = []
    values: list[Any] = []

    query = (params.get("q") or [""])[0].strip()
    words = _search_words(query)
    for word in words:
        pattern = f"%{word}%"
        clauses.append(
            """
            (
                lower(v.title) LIKE ? OR
                lower(v.company) LIKE ? OR
                lower(v.place) LIKE ? OR
                lower(v.description_text) LIKE ? OR
                lower(v.salary_text) LIKE ?
            )
            """
        )
        values.extend([pattern, pattern, pattern, pattern, pattern])

    sources = _request_values(params, "source")
    if sources:
        placeholders = ", ".join("?" for _ in sources)
        clauses.append(f"v.source IN ({placeholders})")
        values.extend(sources)

    location = (params.get("location") or [""])[0].strip().lower()
    if location:
        location_terms = location_search_terms(location) or [location]
        clauses.append("(" + " OR ".join("lower(v.place) LIKE ?" for _ in location_terms) + ")")
        values.extend(f"%{term}%" for term in location_terms)

    company = (params.get("company") or [""])[0].strip().lower()
    if company:
        clauses.append("lower(v.company) LIKE ?")
        values.append(f"%{company}%")

    salary_min = _request_int(params, "salary_min")
    salary_max = _request_int(params, "salary_max")
    if salary_min is not None or salary_max is not None or (params.get("has_salary") or [""])[0] == "1":
        clauses.append("(v.salary_min IS NOT NULL OR v.salary_max IS NOT NULL)")
    if salary_min is not None:
        clauses.append("COALESCE(v.salary_max, v.salary_min) >= ?")
        values.append(salary_min)
    if salary_max is not None:
        clauses.append("COALESCE(v.salary_min, v.salary_max) <= ?")
        values.append(salary_max)

    date_from = _request_date(params, "date_from")
    date_to = _request_date(params, "date_to")
    if date_from or date_to:
        date_field = (params.get("date_field") or ["last_seen"])[0].strip()
        date_expression, require_iso_date = _date_filter_expression(date_field)
        if require_iso_date:
            clauses.append(f"{date_expression} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'")
        if date_from:
            clauses.append(f"{date_expression} >= ?")
            values.append(date_from)
        if date_to:
            clauses.append(f"{date_expression} <= ?")
            values.append(date_to)

    role = (params.get("role") or [""])[0].strip().lower()
    if role:
        clauses.append(
            """
            EXISTS (
                SELECT 1 FROM vacancy_terms vt
                WHERE vt.vacancy_id = v.vacancy_id
                  AND vt.term_type IN ('role_family_primary', 'role_family')
                  AND lower(vt.term_value) = ?
            )
            """
        )
        values.append(role)

    skills = [value.lower() for value in _request_values(params, "skill")]
    for skill in skills:
        placeholders = ", ".join("?" for _ in TECH_TERM_TYPES)
        clauses.append(
            f"""
            EXISTS (
                SELECT 1 FROM vacancy_terms vt
                WHERE vt.vacancy_id = v.vacancy_id
                  AND vt.term_type IN ({placeholders})
                  AND lower(vt.term_value) = ?
            )
            """
        )
        values.extend(sorted(TECH_TERM_TYPES))
        values.append(skill)

    keywords = [value.lower() for value in _request_values(params, "keyword")]
    for keyword in keywords:
        pattern = f"%{keyword}%"
        clauses.append(
            """
            (
                EXISTS (
                    SELECT 1 FROM vacancy_terms vt
                    WHERE vt.vacancy_id = v.vacancy_id
                      AND lower(vt.term_value) LIKE ?
                ) OR
                lower(v.keywords_matched_json) LIKE ? OR
                lower(v.analytics_json) LIKE ?
            )
            """
        )
        values.extend([pattern, pattern, pattern])

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(f"({clause.strip()})" for clause in clauses)
    return where, values, [*words, *keywords]


def search_local_databases(
    database_paths: Iterable[Path],
    params: dict[str, list[str]],
) -> dict[str, Any]:
    legacy_limit = _request_int(params, "limit", SEARCH_DEFAULT_PAGE_SIZE) or SEARCH_DEFAULT_PAGE_SIZE
    per_page = _request_int(params, "per_page", legacy_limit) or SEARCH_DEFAULT_PAGE_SIZE
    per_page = max(1, min(per_page, SEARCH_MAX_PAGE_SIZE))
    page = _request_int(params, "page", 1) or 1
    page = max(1, page)
    where, values, words = _build_where(params)
    rows: list[dict[str, Any]] = []
    database_errors: list[dict[str, str]] = []
    selected_seniority = (params.get("seniority") or [""])[0].strip().lower()

    query = f"""
        SELECT
            v.vacancy_id,
            v.source,
            v.title,
            v.company,
            v.place,
            v.publication_date,
            v.initial_publication_date,
            v.url,
            v.employment_type,
            v.salary_min,
            v.salary_max,
            v.salary_currency,
            v.salary_unit,
            v.salary_text,
            v.keywords_matched_json,
            v.raw_json,
            v.analytics_json,
            v.job_posting_schema_json,
            v.detail_schema_error,
            v.detail_schema_skipped,
            v.llm_analysis_json,
            v.llm_model,
            v.llm_analyzed_at,
            v.first_seen_at,
            v.last_seen_at,
            v.description_text
        FROM vacancies v
        {where}
        ORDER BY
            v.last_seen_at DESC,
            COALESCE(v.salary_max, v.salary_min) DESC,
            v.vacancy_id ASC
    """

    for database_path in database_paths:
        try:
            connection = _connect_readonly(database_path)
            try:
                fetched = connection.execute(query, values).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            database_errors.append({"database": str(database_path), "error": str(exc)})
            continue

        for row in fetched:
            analytics = _load_json_object(row["analytics_json"])
            matched_keywords = _load_json_list(row["keywords_matched_json"])
            detected_seniority = _listify(analytics.get("seniority_labels"))
            effective_seniority = _select_effective_seniority(row["title"], detected_seniority)
            if selected_seniority and effective_seniority != selected_seniority:
                continue
            skills = []
            for key in ("programming_languages", "frameworks_libraries", "cloud_platforms", "databases", "tools"):
                skills.extend(_listify(analytics.get(key)))
            rows.append(
                {
                    "database": str(database_path),
                    "id": row["vacancy_id"],
                    "source": row["source"],
                    "title": row["title"] or "",
                    "company": row["company"] or "",
                    "location": normalize_location_display(row["place"]) or row["place"] or "",
                    "publication_date": row["publication_date"] or row["initial_publication_date"] or "",
                    "url": row["url"] or "",
                    "employment_type": row["employment_type"] or "",
                    "salary_min": row["salary_min"],
                    "salary_max": row["salary_max"],
                    "salary_currency": row["salary_currency"] or "",
                    "salary_unit": row["salary_unit"] or "",
                    "salary": _format_salary(row),
                    "last_seen_at": row["last_seen_at"] or "",
                    "role": analytics.get("role_family_primary") or "",
                    "seniority": effective_seniority,
                    "detected_seniority": ", ".join(detected_seniority),
                    "remote_mode": analytics.get("remote_mode") or "",
                    "matched_keywords": matched_keywords[:10],
                    "skills": sorted({str(skill) for skill in skills if str(skill).strip()})[:10],
                    "score": _row_score(row, words),
                    "description_text": str(row["description_text"] or "").strip(),
                    "description_preview": str(row["description_text"] or "").strip()[:420],
                    "analytics": analytics,
                    "raw": _load_json_object(row["raw_json"]),
                    "job_posting_schema": _load_json_object(row["job_posting_schema_json"]),
                    "detail_schema_error": row["detail_schema_error"] or "",
                    "detail_schema_skipped": bool(row["detail_schema_skipped"]),
                    "llm_analysis": _load_json_object(row["llm_analysis_json"]),
                    "llm_model": row["llm_model"] or "",
                    "llm_analyzed_at": row["llm_analyzed_at"] or "",
                }
            )

    rows.sort(
        key=lambda item: (
            int(item["score"]),
            str(item["last_seen_at"]),
            item["salary_max"] if isinstance(item["salary_max"], int) else item["salary_min"] or -1,
        ),
        reverse=True,
    )
    total = len(rows)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    end = start + per_page
    page_rows = rows[start:end]
    return {
        "count": total,
        "shown_count": len(page_rows),
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "results": page_rows,
        "database_errors": database_errors,
    }


def load_facets(database_paths: Iterable[Path]) -> dict[str, Any]:
    sources: dict[str, int] = {}
    locations: dict[str, int] = {}
    terms: dict[str, dict[str, int]] = {term_type: {} for term_type in FACET_TERM_TYPES}
    database_stats: list[dict[str, Any]] = []
    total = 0
    database_errors: list[dict[str, str]] = []

    for database_path in database_paths:
        try:
            connection = _connect_readonly(database_path)
            try:
                database_count = int(connection.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0])
                total += database_count
                database_stats.append(
                    {
                        "label": _database_label(database_path),
                        "path": str(database_path),
                        "count": database_count,
                    }
                )
                for row in connection.execute(
                    """
                    SELECT source, COUNT(*) AS item_count
                    FROM vacancies
                    GROUP BY source
                    """
                ):
                    source = str(row["source"] or "")
                    if source:
                        sources[source] = sources.get(source, 0) + int(row["item_count"])

                for row in connection.execute(
                    """
                    SELECT place, COUNT(*) AS item_count
                    FROM vacancies
                    WHERE place IS NOT NULL AND trim(place) != ''
                    GROUP BY place
                    ORDER BY item_count DESC
                    LIMIT 150
                    """
                ):
                    place = normalize_location_display(row["place"])
                    if place:
                        locations[place] = locations.get(place, 0) + int(row["item_count"])

                placeholders = ", ".join("?" for _ in FACET_TERM_TYPES)
                for row in connection.execute(
                    f"""
                    SELECT term_type, lower(term_value) AS term_value, COUNT(*) AS item_count
                    FROM vacancy_terms
                    WHERE term_type IN ({placeholders})
                      AND term_value IS NOT NULL
                      AND trim(term_value) != ''
                    GROUP BY term_type, lower(term_value)
                    ORDER BY item_count DESC
                    """,
                    sorted(FACET_TERM_TYPES),
                ):
                    term_type = str(row["term_type"] or "")
                    term_value = str(row["term_value"] or "")
                    if term_type in terms and term_value:
                        terms[term_type][term_value] = terms[term_type].get(term_value, 0) + int(row["item_count"])
            finally:
                connection.close()
        except sqlite3.Error as exc:
            database_errors.append({"database": str(database_path), "error": str(exc)})

    def top_items(items: dict[str, int], limit: int) -> list[dict[str, Any]]:
        return [
            {"value": value, "count": count}
            for value, count in sorted(items.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]

    return {
        "total": total,
        "databases": [str(path) for path in database_paths],
        "database_stats": sorted(database_stats, key=lambda item: (-int(item["count"]), str(item["label"]))),
        "sources": top_items(sources, 30),
        "locations": top_items(locations, 80),
        "terms": {term_type: top_items(values, 80) for term_type, values in terms.items()},
        "database_errors": database_errors,
    }


def render_index(database_paths: Iterable[Path]) -> str:
    database_list = "\n".join(
        f"<li>{html.escape(str(path))}</li>" for path in database_paths
    )
    return INDEX_HTML.replace("__DATABASE_LIST__", database_list)


class LocalSearchHandler(BaseHTTPRequestHandler):
    config: LocalSearchConfig

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/search"}:
            _head_response(self, "text/html; charset=utf-8")
            return
        if parsed.path in {
            "/api/search",
            "/api/facets",
            "/api/parser-runs",
            "/api/ai-analysis-runs",
            "/api/public-stats-runs",
            "/api/resume-match",
            "/health",
        }:
            _head_response(self, "application/json; charset=utf-8")
            return
        _head_response(self, "text/plain; charset=utf-8", status=HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        try:
            if parsed.path in {"/", "/search"}:
                _html_response(self, render_index(self.config.database_paths))
                return
            if parsed.path == "/api/search":
                _json_response(self, search_local_databases(self.config.database_paths, params))
                return
            if parsed.path == "/api/facets":
                _json_response(self, load_facets(self.config.database_paths))
                return
            if parsed.path == "/api/parser-runs":
                run_id = (params.get("run_id") or [""])[0].strip()
                after = _request_int(params, "after", 0) or 0
                _json_response(self, get_parser_run(run_id, after_seq=after))
                return
            if parsed.path == "/api/ai-analysis-runs":
                run_id = (params.get("run_id") or [""])[0].strip()
                after = _request_int(params, "after", 0) or 0
                _json_response(self, get_ai_analysis_run(run_id, after_seq=after))
                return
            if parsed.path == "/api/public-stats-runs":
                run_id = (params.get("run_id") or [""])[0].strip()
                after = _request_int(params, "after", 0) or 0
                _json_response(self, get_public_stats_run(run_id, after_seq=after))
                return
            if parsed.path == "/health":
                _json_response(self, {"ok": True})
                return
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        _text_response(self, "Not found", status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/api/parser-runs":
                _json_response(self, start_parser_run(_json_body(self)), status=HTTPStatus.CREATED)
                return
            if parsed.path == "/api/ai-analysis-runs":
                _json_response(self, start_ai_analysis_run(_json_body(self)), status=HTTPStatus.CREATED)
                return
            if parsed.path == "/api/public-stats-runs":
                _json_response(self, start_public_stats_run(_json_body(self)), status=HTTPStatus.CREATED)
                return
            if parsed.path == "/api/resume-match":
                _json_response(self, build_resume_match(self.config.database_paths, _json_body(self)))
                return
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        _text_response(self, "Not found", status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[local-search] {self.address_string()} {format % args}", file=sys.stderr)


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local Vacancy Search</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #121722;
      --muted: #657182;
      --line: #e5e7eb;
      --field: #ffffff;
      --surface: #fafafa;
      --panel: #ffffff;
      --accent: #d71920;
      --accent-dark: #b71118;
      --accent-soft: rgba(215, 25, 32, 0.08);
      --green: #d71920;
      --blue: #17202a;
      --amber: #d71920;
      --shadow: 0 10px 30px rgba(17, 24, 39, 0.07);
      --shadow-soft: 0 4px 14px rgba(17, 24, 39, 0.05);
    }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--surface);
      color: var(--ink);
      letter-spacing: 0;
    }
    button, input, select, textarea { font: inherit; }
    a { color: inherit; text-decoration: none; }
    .app {
      max-width: 1480px;
      margin: 0 auto;
      padding: 24px 44px 32px;
      display: grid;
      grid-template-columns: 330px minmax(0, 1fr);
      gap: 24px;
      align-items: start;
    }
    .app.view-search,
    .app.view-ai-analyse,
    .app.view-resume-matcher,
    .app.view-public-stats,
    .app.view-settings {
      grid-template-columns: minmax(0, 1fr);
    }
    .app.view-search .filters-panel,
    .app.view-ai-analyse .filters-panel,
    .app.view-resume-matcher .filters-panel,
    .app.view-public-stats .filters-panel,
    .app.view-settings .filters-panel {
      display: none;
    }
    .main-menu {
      grid-column: 1 / -1;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px 20px;
      box-shadow: var(--shadow);
      display: grid;
      grid-template-columns: minmax(180px, 240px) minmax(0, 1fr);
      gap: 18px;
      align-items: center;
    }
    .brand {
      display: grid;
      gap: 4px;
    }
    .brand-title {
      margin: 0;
      color: var(--ink);
      font-size: 16px;
      font-weight: 900;
      line-height: 1.2;
    }
    .brand-sub {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .menu-list {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 8px;
    }
    .menu-btn {
      width: 100%;
      min-height: 42px;
      border: 1px solid transparent;
      border-radius: 6px;
      background: transparent;
      color: #344150;
      cursor: pointer;
      display: grid;
      grid-template-columns: 28px minmax(0, 1fr);
      align-items: center;
      gap: 10px;
      padding: 0 10px;
      text-align: left;
      font-size: 14px;
      font-weight: 800;
    }
    .menu-btn:hover,
    .menu-btn.is-active {
      border-color: rgba(215, 25, 32, 0.2);
      background: var(--accent-soft);
      color: var(--accent);
    }
    .menu-icon {
      width: 28px;
      height: 28px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #f3f4f6;
      color: #17202a;
      font-size: 14px;
      line-height: 1;
    }
    .menu-btn.is-active .menu-icon {
      background: linear-gradient(180deg, #e03136, #c9161d);
      color: #fff;
      box-shadow: 0 8px 18px rgba(215, 25, 32, 0.18);
    }
    .filters-panel {
      position: sticky;
      top: 24px;
      max-height: calc(100vh - 48px);
      overflow: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
      box-shadow: var(--shadow);
    }
    main {
      min-width: 0;
      padding: 10px 0 32px;
    }
    .workspace-panel[hidden] {
      display: none;
    }
    h1 {
      margin: 0 0 4px;
      font-size: 20px;
      line-height: 1.2;
      letter-spacing: -0.03em;
    }
    .sub {
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .field { margin-bottom: 14px; }
    label {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: #151b28;
      font-size: 13px;
      font-weight: 800;
      margin-bottom: 9px;
    }
    input, select, textarea {
      width: 100%;
      min-height: 44px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--field);
      color: var(--ink);
      padding: 10px 12px;
      outline: none;
      font-size: 14px;
      box-shadow: inset 0 1px 0 rgba(17, 24, 39, 0.02);
    }
    textarea {
      min-height: 44px;
      resize: none;
    }
    input:focus, select:focus, textarea:focus {
      border-color: rgba(215, 25, 32, 0.5);
      box-shadow: 0 0 0 3px rgba(215, 25, 32, 0.1);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .actions {
      display: grid;
      gap: 14px;
      margin-top: 20px;
    }
    .btn {
      min-height: 46px;
      border: 1px solid transparent;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 0 14px;
      white-space: nowrap;
    }
    .btn.primary {
      background: linear-gradient(180deg, #e03136, #c9161d);
      color: white;
      box-shadow: 0 8px 18px rgba(215, 25, 32, 0.18);
    }
    .btn.primary:hover { background: var(--accent-dark); }
    .btn.secondary {
      background: #ffffff;
      border-color: var(--accent);
      color: var(--accent);
    }
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
      position: relative;
    }
    .toolbar h1 {
      font-size: 16px;
      font-weight: 500;
      letter-spacing: 0;
    }
    .toolbar h1 strong {
      color: var(--accent);
      font-weight: 800;
    }
    .sort-control {
      min-width: 156px;
      width: auto;
      background-position: right 12px center;
    }
    .toolbar-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .section-kicker {
      margin: 0 0 6px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 900;
      line-height: 1.2;
      text-transform: uppercase;
    }
    .settings-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }
    .settings-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 18px;
      box-shadow: var(--shadow-soft);
    }
    .settings-panel h2 {
      margin: 0 0 6px;
      color: #17202a;
      font-size: 15px;
      line-height: 1.3;
    }
    .settings-panel p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .settings-row {
      display: grid;
      gap: 10px;
      margin-top: 16px;
    }
    .setting-toggle {
      min-height: 42px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 12px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
      color: #344150;
      font-size: 13px;
      font-weight: 800;
    }
    .switch {
      width: 44px;
      height: 24px;
      border-radius: 999px;
      background: #e5e7eb;
      position: relative;
    }
    .switch::after {
      content: "";
      position: absolute;
      top: 4px;
      left: 4px;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: #fff;
      box-shadow: 0 2px 8px rgba(17, 24, 39, 0.14);
    }
    .switch.is-on {
      background: linear-gradient(180deg, #e03136, #c9161d);
    }
    .switch.is-on::after {
      left: 24px;
    }
    .parser-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
      gap: 12px;
      margin-top: 16px;
    }
    .parser-panel {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 18px;
      box-shadow: var(--shadow-soft);
    }
    .parser-panel h2 {
      margin: 0 0 6px;
      color: #17202a;
      font-size: 15px;
      line-height: 1.3;
    }
    .parser-panel p {
      margin: 0 0 16px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .parser-preview {
      display: grid;
      gap: 10px;
    }
    .resume-toolbar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(320px, 0.9fr);
      gap: 18px;
      align-items: end;
    }
    .resume-status-cards {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .resume-status-card {
      min-height: 82px;
      display: grid;
      grid-template-columns: 36px minmax(0, 1fr);
      gap: 12px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 16px;
      box-shadow: var(--shadow-soft);
    }
    .resume-status-card strong {
      display: block;
      color: #17202a;
      font-size: 12px;
      line-height: 1.25;
    }
    .resume-status-card span:last-child {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.25;
    }
    .resume-status-icon {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #f3f4f6;
      color: #17202a;
      font-size: 16px;
      font-weight: 900;
    }
    .resume-grid {
      display: grid;
      gap: 18px;
      margin-top: 16px;
      align-items: start;
    }
    .resume-form,
    .resume-output {
      display: grid;
      gap: 18px;
    }
    .resume-panel {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 18px;
      box-shadow: var(--shadow-soft);
    }
    .resume-panel h2 {
      margin: 0 0 6px;
      color: #17202a;
      font-size: 15px;
      line-height: 1.3;
    }
    .resume-panel p {
      margin: 0 0 16px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .resume-input-cards {
      display: grid;
      grid-template-columns: minmax(0, 0.95fr) minmax(0, 1fr);
      gap: 12px;
      align-items: stretch;
    }
    .resume-card {
      display: grid;
      align-content: start;
    }
    .resume-segment {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      margin-bottom: 16px;
    }
    .resume-segment button {
      min-height: 42px;
      border: 0;
      border-right: 1px solid var(--line);
      background: #fff;
      color: #344150;
      cursor: pointer;
      font-size: 13px;
      font-weight: 800;
    }
    .resume-segment button:last-child {
      border-right: 0;
    }
    .resume-segment button.is-active {
      background: var(--accent-soft);
      color: var(--accent);
      box-shadow: inset 0 0 0 1px rgba(215, 25, 32, 0.18);
    }
    .resume-input-grid {
      display: grid;
      gap: 12px;
      align-items: start;
    }
    .resume-input-grid .field,
    .resume-card .field {
      margin-bottom: 0;
    }
    .resume-url-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: end;
    }
    .resume-inline-status {
      display: inline-flex;
      width: fit-content;
      align-items: center;
      min-height: 26px;
      border-radius: 999px;
      margin-top: 8px;
      background: #eef9f0;
      color: #1f9d3a;
      padding: 0 10px;
      font-size: 12px;
      font-weight: 800;
    }
    .resume-inline-status.is-muted {
      background: #f3f4f6;
      color: var(--muted);
    }
    .resume-form textarea {
      min-height: 132px;
      resize: vertical;
    }
    .resume-file-zone {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 8px;
    }
    .resume-file-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }
    .resume-file-input {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0 0 0 0);
      white-space: nowrap;
      clip-path: inset(50%);
    }
    .resume-upload-label {
      min-height: 42px;
      border: 1px solid rgba(215, 25, 32, 0.34);
      border-radius: 6px;
      background: var(--accent-soft);
      color: var(--accent);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 0 14px;
      font-size: 13px;
      font-weight: 900;
    }
    .resume-file-name {
      margin: 0;
      color: #17202a;
      font-size: 13px;
      line-height: 1.35;
      font-weight: 800;
      overflow-wrap: anywhere;
    }
    .resume-file-hint {
      display: block;
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
    }
    .resume-drop-hint {
      display: grid;
      place-items: center;
      min-height: 82px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      margin-top: 8px;
      color: var(--muted);
      text-align: center;
      font-size: 12px;
      line-height: 1.5;
    }
    .resume-form #resume_text {
      min-height: 160px;
    }
    .resume-preview-panel {
      display: grid;
      gap: 14px;
    }
    .resume-preview-head,
    .resume-result-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
    }
    .resume-vacancy-preview {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 18px;
    }
    .resume-vacancy-preview h3 {
      margin: 0 0 10px;
      color: #111827;
      font-size: 16px;
      line-height: 1.35;
    }
    .resume-preview-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 14px;
    }
    .resume-vacancy-preview p {
      margin: 0;
      color: #344150;
      font-size: 13px;
      line-height: 1.65;
    }
    .resume-action-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 10px;
      margin-top: 0;
    }
    .resume-analysis-grid {
      display: grid;
      grid-template-columns: 0.82fr 1fr 1.18fr;
      gap: 16px;
      align-items: stretch;
    }
    .resume-report-section {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 18px;
      box-shadow: var(--shadow-soft);
    }
    .resume-score {
      display: grid;
      grid-template-columns: 94px minmax(0, 1fr);
      gap: 16px;
      align-items: center;
      margin-bottom: 18px;
    }
    .resume-score-value {
      --score: 0;
      width: 84px;
      height: 84px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background:
        radial-gradient(circle at center, #fff 56%, transparent 57%),
        conic-gradient(#2ea84a calc(var(--score) * 1%), #e5e7eb 0);
      color: #2ea84a;
      font-size: 22px;
      font-weight: 900;
    }
    .resume-score h2 {
      margin: 0 0 4px;
      color: #2ea84a;
      font-size: 15px;
      line-height: 1.3;
    }
    .resume-score p,
    .resume-note {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .resume-metric-list {
      display: grid;
      gap: 10px;
    }
    .resume-metric {
      display: grid;
      gap: 6px;
    }
    .resume-metric-row {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: #17202a;
      font-size: 12px;
      font-weight: 800;
    }
    .resume-meter {
      height: 6px;
      border-radius: 999px;
      background: #eef0f3;
      overflow: hidden;
    }
    .resume-meter span {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: #2ea84a;
    }
    .resume-meter.is-warm span {
      background: #f59e0b;
    }
    .resume-keyword-columns {
      display: grid;
      gap: 16px;
    }
    .resume-recommendation-list {
      display: grid;
      gap: 10px;
    }
    .resume-recommendation {
      display: grid;
      grid-template-columns: 36px minmax(0, 1fr);
      gap: 12px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }
    .resume-recommendation-icon {
      width: 30px;
      height: 30px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #eef5ff;
      color: #2563eb;
      font-size: 14px;
      font-weight: 900;
    }
    .resume-recommendation strong {
      display: block;
      color: #17202a;
      font-size: 13px;
      line-height: 1.35;
    }
    .resume-recommendation span:last-child {
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .resume-output-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 0.95fr);
      gap: 18px;
      align-items: start;
    }
    .resume-download-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .resume-download-card,
    .resume-copy-card {
      min-height: 72px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8fbff;
      color: #1d4ed8;
      display: grid;
      grid-template-columns: 36px minmax(0, 1fr);
      gap: 12px;
      align-items: center;
      padding: 14px;
      font-size: 13px;
      font-weight: 900;
      text-align: left;
      box-shadow: var(--shadow-soft);
    }
    .resume-download-card {
      border-color: rgba(215, 25, 32, 0.24);
      background: #fff8f8;
      color: var(--accent);
    }
    .resume-download-card[hidden] {
      display: none;
    }
    .resume-download-card small,
    .resume-copy-card small {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 600;
    }
    .resume-download-icon {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: currentColor;
      color: #fff;
      font-size: 13px;
      font-weight: 900;
    }
    .resume-result-text {
      width: 100%;
      min-height: 96px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .resume-tip {
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      background: #eff6ff;
      color: #1d4ed8;
      padding: 12px 14px;
      font-size: 13px;
      line-height: 1.45;
    }
    .keyword-cloud {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }
    .resume-result-text {
      width: 100%;
      min-height: 420px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .log-toggle {
      position: absolute;
      top: 50%;
      left: -44px;
      width: 44px;
      height: 104px;
      border: 1px solid rgba(215, 25, 32, 0.22);
      border-right: 1px solid rgba(215, 25, 32, 0.22);
      border-radius: 8px 0 0 8px;
      background: linear-gradient(180deg, #e03136, #c9161d);
      color: #fff;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 14px 32px rgba(17, 24, 39, 0.16);
      transform: translateY(-50%);
      font-size: 18px;
      font-weight: 900;
    }
    .log-toggle:hover,
    .log-toggle[aria-expanded="true"] {
      background: var(--accent-dark);
    }
    .log-drawer {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: 39;
      width: min(380px, calc(100vw - 48px));
      border-left: 1px solid var(--line);
      background: #fff;
      box-shadow: -18px 0 42px rgba(17, 24, 39, 0.14);
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
      transform: translateX(100%);
      transition: transform 160ms ease;
    }
    .log-drawer.is-open {
      transform: translateX(0);
    }
    .log-head {
      min-height: 70px;
      border-bottom: 1px solid var(--line);
      padding: 18px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
    }
    .log-title {
      margin: 0 0 4px;
      color: #17202a;
      font-size: 15px;
      line-height: 1.25;
      font-weight: 900;
    }
    .log-subtitle {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .log-close {
      width: 32px;
      height: 32px;
      min-height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: #17202a;
      cursor: pointer;
      font-weight: 900;
    }
    .log-list {
      min-height: 0;
      overflow: auto;
      padding: 14px 18px;
      display: grid;
      align-content: start;
      gap: 10px;
      background: #fafafa;
    }
    .log-entry {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 10px 12px;
      box-shadow: var(--shadow-soft);
    }
    .log-entry.is-info { border-left: 3px solid #17202a; }
    .log-entry.is-success { border-left: 3px solid var(--accent); }
    .log-entry.is-warning { border-left: 3px solid #d97706; }
    .log-entry.is-error { border-left: 3px solid #8e1d23; }
    .log-entry-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 4px;
    }
    .log-entry-title {
      color: #17202a;
      font-size: 12px;
      font-weight: 900;
      line-height: 1.25;
      text-transform: uppercase;
    }
    .log-entry-time {
      color: var(--muted);
      font-size: 11px;
      line-height: 1.2;
      white-space: nowrap;
    }
    .log-entry-message {
      margin: 0;
      color: #344150;
      font-size: 12px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .log-actions {
      border-top: 1px solid var(--line);
      padding: 12px 18px;
      display: flex;
      justify-content: flex-end;
      background: #fff;
    }
    .log-clear {
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: #17202a;
      cursor: pointer;
      padding: 0 12px;
      font-size: 12px;
      font-weight: 800;
    }
    .source-table {
      width: 100%;
      table-layout: fixed;
      border-collapse: separate;
      border-spacing: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      margin: 0 0 16px;
      background: #fff;
    }
    .source-table th,
    .source-table td {
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      color: #344150;
      font-size: 13px;
      line-height: 1.35;
      text-align: left;
      vertical-align: middle;
      overflow-wrap: anywhere;
    }
    .source-table th:first-child,
    .source-table td:first-child {
      width: 56px;
      text-align: center;
    }
    .source-table th:last-child,
    .source-table td:last-child {
      width: 84px;
    }
    .source-table th {
      background: #f8fafc;
      color: #17202a;
      font-size: 12px;
      font-weight: 900;
      text-transform: uppercase;
    }
    .source-table tr:last-child td {
      border-bottom: 0;
    }
    .source-check {
      width: 18px;
      height: 18px;
      min-height: 18px;
      padding: 0;
      accent-color: var(--accent);
      box-shadow: none;
    }
    .source-name {
      color: #17202a;
      font-weight: 900;
    }
    .source-status {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      padding: 0 9px;
      font-size: 12px;
      font-weight: 900;
      white-space: nowrap;
    }
    .parser-step {
      display: grid;
      grid-template-columns: 32px minmax(0, 1fr);
      gap: 10px;
      align-items: start;
      border-top: 1px solid var(--line);
      padding-top: 12px;
      color: #344150;
      font-size: 13px;
      line-height: 1.45;
    }
    .step-index {
      width: 32px;
      height: 32px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 900;
    }
    .step-title {
      display: block;
      color: #17202a;
      font-weight: 900;
      margin-bottom: 2px;
    }
    .info-menu {
      position: relative;
      margin: 0;
      color: inherit;
      font-size: inherit;
    }
    .info-menu summary {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: linear-gradient(180deg, #e03136, #c9161d);
      color: #fff;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 15px;
      font-weight: 900;
      line-height: 1;
      list-style: none;
      box-shadow: 0 8px 18px rgba(215, 25, 32, 0.18);
      user-select: none;
    }
    .info-menu summary::-webkit-details-marker {
      display: none;
    }
    .info-menu[open] summary {
      background: var(--accent-dark);
    }
    .stats {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .pill {
      min-height: 28px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 0;
      border-radius: 0;
      background: #ffffff;
      padding: 0;
    }
    .database-summary {
      position: absolute;
      top: 42px;
      right: 0;
      z-index: 15;
      width: min(290px, calc(100vw - 32px));
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 12px;
      box-shadow: 0 18px 42px rgba(17, 24, 39, 0.12);
    }
    .summary-block {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 12px;
      box-shadow: var(--shadow-soft);
    }
    .summary-title {
      margin: 0 0 8px;
      color: #344150;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .summary-list {
      display: grid;
      gap: 7px;
      margin: 0;
    }
    .summary-item {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      color: #344150;
      font-size: 13px;
      line-height: 1.25;
    }
    .summary-item span:first-child {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .summary-count {
      color: var(--ink);
      font-weight: 800;
    }
    .results {
      display: grid;
      gap: 12px;
    }
    .pagination {
      display: flex;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 22px;
    }
    .page-btn {
      min-width: 36px;
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: #17202a;
      cursor: pointer;
      font-size: 14px;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0 10px;
      box-shadow: var(--shadow-soft);
    }
    .page-btn:hover:not(:disabled),
    .page-btn.is-active {
      border-color: var(--accent);
      background: linear-gradient(180deg, #e03136, #c9161d);
      color: #fff;
    }
    .page-btn:disabled {
      cursor: not-allowed;
      opacity: 0.45;
      box-shadow: none;
    }
    .page-gap {
      min-width: 24px;
      color: var(--muted);
      text-align: center;
      font-weight: 800;
    }
    .job {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 24px 24px 20px;
      box-shadow: var(--shadow-soft);
    }
    .job-head {
      display: grid;
      grid-template-columns: 54px minmax(0, 1fr) minmax(160px, auto);
      gap: 18px;
      align-items: start;
    }
    .company-mark {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: linear-gradient(180deg, #e03136, #c9161d);
      color: #fff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      font-weight: 800;
      box-shadow: 0 8px 16px rgba(215, 25, 32, 0.18);
      text-transform: uppercase;
    }
    .job h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.28;
      letter-spacing: -0.02em;
    }
    .company {
      margin-top: 4px;
      color: #151b28;
      font-size: 14px;
      font-weight: 600;
    }
    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 7px 12px;
      color: var(--muted);
      font-size: 13px;
      margin-top: 8px;
    }
    .meta span + span::before {
      content: "";
      width: 3px;
      height: 3px;
      border-radius: 50%;
      background: #c2c8d0;
      display: inline-block;
      margin-right: 12px;
      vertical-align: middle;
    }
    .job-side {
      display: grid;
      justify-items: end;
      gap: 14px;
      text-align: right;
    }
    .job-actions {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
    }
    .salary {
      color: var(--green);
      font-weight: 800;
      white-space: nowrap;
      font-size: 14px;
    }
    .tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 14px;
      margin-left: 72px;
    }
    .tag {
      border-radius: 999px;
      background: #f3f4f6;
      color: #4b5563;
      padding: 4px 9px;
      font-size: 12px;
      line-height: 1.2;
    }
    .tag.role { background: var(--accent-soft); color: var(--accent); }
    .tag.warn { background: #fff4f4; color: #a3161b; }
    .tag.keyword { background: #f5f5f5; color: #374151; }
    .preview {
      color: #4b5968;
      font-size: 13px;
      line-height: 1.5;
      margin: 12px 0 0 72px;
      max-width: 620px;
    }
    .open-link {
      min-height: 36px;
      border-radius: 6px;
      border: 1px solid transparent;
      padding: 0 18px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(180deg, #e03136, #c9161d);
      color: #fff;
      text-decoration: none;
      font-weight: 800;
      white-space: nowrap;
      font-size: 13px;
      box-shadow: 0 8px 18px rgba(215, 25, 32, 0.18);
    }
    .details-toggle {
      min-height: 36px;
      border-radius: 6px;
      border: 1px solid var(--line);
      padding: 0 14px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #fff;
      color: #17202a;
      cursor: pointer;
      font-weight: 800;
      white-space: nowrap;
      font-size: 13px;
      box-shadow: var(--shadow-soft);
    }
    .details-toggle:hover,
    .details-toggle[aria-expanded="true"] {
      border-color: var(--accent);
      color: var(--accent);
    }
    .json-toggle {
      margin-top: 14px;
    }
    .job-details-panel {
      margin: 16px 0 0 72px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 16px;
      color: #344150;
      box-shadow: var(--shadow-soft);
    }
    .job-details-panel[hidden] {
      display: none;
    }
    .details-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px 16px;
      margin: 0 0 14px;
    }
    .detail-item {
      min-width: 0;
    }
    .detail-label {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      margin-bottom: 3px;
    }
    .detail-value {
      color: #17202a;
      font-size: 13px;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }
    .detail-section {
      border-top: 1px solid var(--line);
      padding-top: 14px;
      margin-top: 14px;
    }
    .detail-section[hidden] {
      display: none;
    }
    .detail-section-title {
      margin: 0 0 8px;
      color: #17202a;
      font-size: 13px;
      font-weight: 800;
    }
    .detail-description {
      margin: 0;
      color: #344150;
      font-size: 13px;
      line-height: 1.55;
      white-space: pre-wrap;
    }
    .detail-json {
      max-height: 260px;
      overflow: auto;
      margin: 0;
      border-radius: 6px;
      background: #f8fafc;
      padding: 12px;
      color: #1f2937;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
    }
    .empty, .error {
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 28px;
      background: #ffffff;
      color: var(--muted);
      text-align: center;
    }
    .error {
      color: #8e1d23;
      border-color: #dfb8bb;
      background: #fff8f8;
    }
    details {
      margin-top: 20px;
      color: var(--muted);
      font-size: 12px;
    }
    details ul {
      margin: 8px 0 0;
      padding-left: 18px;
      overflow-wrap: anywhere;
    }
    .salary-range {
      padding-top: 2px;
    }
    .range-control {
      position: relative;
      height: 30px;
      margin: 2px 0 8px;
    }
    .range-track {
      position: absolute;
      left: 8px;
      right: 8px;
      top: 14px;
      height: 4px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), var(--accent));
    }
    input[type="range"] {
      position: absolute;
      inset: 0;
      min-height: 30px;
      padding: 0;
      border: 0;
      background: transparent;
      box-shadow: none;
      appearance: none;
      pointer-events: none;
    }
    input[type="range"]::-webkit-slider-thumb {
      appearance: none;
      width: 18px;
      height: 18px;
      border: 1px solid var(--accent);
      border-radius: 50%;
      background: #fff;
      cursor: pointer;
      pointer-events: auto;
      box-shadow: 0 2px 8px rgba(215, 25, 32, 0.16);
    }
    input[type="range"]::-moz-range-thumb {
      width: 18px;
      height: 18px;
      border: 1px solid var(--accent);
      border-radius: 50%;
      background: #fff;
      cursor: pointer;
      pointer-events: auto;
      box-shadow: 0 2px 8px rgba(215, 25, 32, 0.16);
    }
    input[type="range"]::-webkit-slider-runnable-track {
      height: 4px;
      background: transparent;
    }
    input[type="range"]::-moz-range-track {
      height: 4px;
      background: transparent;
    }
    .range-values {
      display: flex;
      justify-content: space-between;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.3;
    }
    @media (max-width: 860px) {
      .app {
        grid-template-columns: 1fr;
        padding: 18px;
        gap: 18px;
      }
      .app.view-search,
      .app.view-ai-analyse,
      .app.view-resume-matcher,
      .app.view-public-stats,
      .app.view-settings {
        grid-template-columns: 1fr;
      }
      .main-menu {
        position: static;
        max-height: none;
        grid-template-columns: 1fr;
      }
      .menu-list {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .filters-panel {
        position: static;
        max-height: none;
      }
      main { padding: 18px; }
      .settings-grid { grid-template-columns: 1fr; }
      .parser-grid { grid-template-columns: 1fr; }
      .resume-toolbar,
      .resume-input-cards,
      .resume-analysis-grid,
      .resume-output-grid { grid-template-columns: 1fr; }
      .resume-status-cards,
      .resume-download-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .job-head { grid-template-columns: 44px minmax(0, 1fr); }
      .job-side {
        grid-column: 2;
        justify-items: start;
        text-align: left;
      }
      .job-actions {
        justify-content: flex-start;
      }
      .tags, .preview, .job-details-panel { margin-left: 62px; }
      .salary { white-space: normal; }
      .database-summary {
        right: 0;
        grid-template-columns: 1fr;
      }
    }
    @media (max-width: 520px) {
      .main-menu { padding: 18px; }
      .menu-list { grid-template-columns: 1fr; }
      .filters-panel { padding: 18px; }
      .row, .actions { grid-template-columns: 1fr; }
      .toolbar { align-items: flex-start; flex-direction: column; }
      .toolbar-actions { width: 100%; justify-content: space-between; }
      .database-summary {
        left: 0;
        right: auto;
        width: calc(100vw - 36px);
      }
      .btn { width: 100%; }
      .resume-status-cards,
      .resume-download-grid,
      .resume-segment,
      .resume-url-row { grid-template-columns: 1fr; }
      .resume-segment button {
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      .resume-segment button:last-child {
        border-bottom: 0;
      }
      .resume-file-row,
      .resume-score,
      .resume-recommendation,
      .resume-status-card,
      .resume-copy-card,
      .resume-download-card {
        grid-template-columns: 1fr;
      }
      main { padding: 0; }
      .job { padding: 18px; }
      .job-head { grid-template-columns: 1fr; }
      .company-mark, .tags, .preview, .job-details-panel { margin-left: 0; }
      .company-mark { border-radius: 8px; }
      .job-side, .job-actions { width: 100%; justify-items: stretch; }
      .job-actions > * { flex: 1 1 130px; }
      .log-toggle {
        width: 40px;
        height: 86px;
        left: -40px;
      }
      .log-drawer {
        width: calc(100vw - 40px);
      }
    }
  </style>
</head>
<body>
  <div class="app view-vacancies" id="app">
    <nav class="main-menu" aria-label="Main application menu">
      <div class="brand">
        <p class="brand-title">Swiss IT Jobs</p>
        <span class="brand-sub">Local database app</span>
      </div>
      <div class="menu-list">
        <button class="menu-btn is-active" type="button" data-view-target="vacancies" aria-current="page">
          <span class="menu-icon" aria-hidden="true">▦</span>
          <span>Vacancy Browser</span>
        </button>
        <button class="menu-btn" type="button" data-view-target="search">
          <span class="menu-icon" aria-hidden="true">⌕</span>
          <span>Vacancy Search</span>
        </button>
        <button class="menu-btn" type="button" data-view-target="ai-analyse">
          <span class="menu-icon" aria-hidden="true">✦</span>
          <span>AI Analyse</span>
        </button>
        <button class="menu-btn" type="button" data-view-target="resume-matcher">
          <span class="menu-icon" aria-hidden="true">▤</span>
          <span>Resume matcher</span>
        </button>
        <button class="menu-btn" type="button" data-view-target="public-stats">
          <span class="menu-icon" aria-hidden="true">◫</span>
          <span>Public Stats</span>
        </button>
        <button class="menu-btn" type="button" data-view-target="settings">
          <span class="menu-icon" aria-hidden="true">⚙</span>
          <span>Settings</span>
        </button>
      </div>
    </nav>
    <aside class="filters-panel">
      <h1>Search Jobs</h1>
      <p class="sub">Searches only your loaded local SQLite databases.</p>
      <form id="search-form" autocomplete="off">
        <div class="field">
          <label for="q">Job title, keywords, or company</label>
          <textarea id="q" name="q" placeholder="python backend zurich"></textarea>
        </div>
        <div class="field">
          <label for="keyword">Keywords</label>
          <input id="keyword" name="keyword" list="keyword-list" placeholder="python, django, kubernetes">
          <datalist id="keyword-list"></datalist>
        </div>
        <div class="row">
          <div class="field">
            <label for="source">Source</label>
            <select id="source" name="source"><option value="">Any</option></select>
          </div>
          <div class="field">
            <label for="location">Location</label>
            <select id="location" name="location"><option value="">Any</option></select>
          </div>
        </div>
        <div class="field">
          <label for="company">Company</label>
          <input id="company" name="company" placeholder="Company name">
        </div>
        <div class="row">
          <div class="field">
            <label for="role">Role</label>
            <select id="role" name="role"><option value="">Any</option></select>
          </div>
          <div class="field">
            <label for="seniority">Seniority</label>
            <select id="seniority" name="seniority"><option value="">Any</option></select>
          </div>
        </div>
        <div class="field">
          <label for="skill">Required skill</label>
          <input id="skill" name="skill" list="skill-list" placeholder="python">
          <datalist id="skill-list"></datalist>
        </div>
        <div class="field">
          <label for="date_field">Date field</label>
          <select id="date_field" name="date_field">
            <option value="last_seen" selected>Last seen</option>
            <option value="first_seen">First seen</option>
            <option value="published">Published</option>
          </select>
        </div>
        <div class="row">
          <div class="field">
            <label for="date_from">Date from</label>
            <input id="date_from" name="date_from" type="text" inputmode="numeric" pattern="\\d{2}\\.\\d{2}\\.\\d{4}" placeholder="dd.mm.yyyy">
          </div>
          <div class="field">
            <label for="date_to">Date to</label>
            <input id="date_to" name="date_to" type="text" inputmode="numeric" pattern="\\d{2}\\.\\d{2}\\.\\d{4}" placeholder="dd.mm.yyyy">
          </div>
        </div>
        <div class="field salary-range">
          <label>Salary Range (CHF)</label>
          <div class="range-control">
            <div class="range-track" id="salary-track"></div>
            <input id="salary_min_range" type="range" min="0" max="250000" step="5000" value="0" aria-label="Salary minimum">
            <input id="salary_max_range" type="range" min="0" max="250000" step="5000" value="250000" aria-label="Salary maximum">
          </div>
          <div class="range-values">
            <span id="salary_min_text">Any min</span>
            <span id="salary_max_text">Any max</span>
          </div>
          <input id="salary_min" name="salary_min" type="hidden">
          <input id="salary_max" name="salary_max" type="hidden">
        </div>
        <div class="field">
          <label for="has_salary">Salary</label>
          <select id="has_salary" name="has_salary">
            <option value="">Any</option>
            <option value="1">Only with salary</option>
          </select>
        </div>
        <div class="actions">
          <button class="btn primary" type="submit" title="Run search">Search</button>
          <button class="btn secondary" type="button" id="reset" title="Clear filters">Clear</button>
        </div>
      </form>
      <details>
        <summary>Loaded local databases</summary>
        <ul>__DATABASE_LIST__</ul>
      </details>
    </aside>
    <main>
      <section class="workspace-panel" id="vacancies-workspace">
        <div class="toolbar">
          <div>
            <p class="section-kicker" id="workspace-kicker">Vacancy Browser</p>
            <h1 id="result-title">Found <strong>0</strong> jobs</h1>
            <p class="sub" id="subtitle">Loading local database facets...</p>
          </div>
          <div class="toolbar-actions">
            <details class="info-menu">
              <summary aria-label="Local database statistics" title="Local database statistics">i</summary>
              <section class="database-summary" id="database-summary" aria-label="Local database statistics"></section>
            </details>
            <select class="sort-control" aria-label="Sort results">
              <option>Most Recent</option>
            </select>
          </div>
        </div>
        <div id="errors"></div>
        <section class="results" id="results"></section>
        <nav class="pagination" id="pagination" aria-label="Search results pages"></nav>
      </section>
      <section class="workspace-panel" id="parser-workspace" hidden>
        <div class="toolbar">
          <div>
            <p class="section-kicker">Vacancy Search</p>
            <h1>Run Vacancy Collection</h1>
            <p class="sub">Visual shell for launching provider parsing and collecting fresh vacancies into local databases.</p>
          </div>
        </div>
        <section class="parser-grid" aria-label="Vacancy collection launcher">
          <form class="parser-panel" autocomplete="off">
            <h2>Collection Parameters</h2>
            <p>Select the provider, search mode, and query fields for a future parser run.</p>
            <table class="source-table" aria-label="Vacancy sources">
              <thead>
                <tr>
                  <th scope="col">Use</th>
                  <th scope="col">Source</th>
                  <th scope="col">Database</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><input class="source-check" type="checkbox" name="parser_source" value="jobs_ch" checked aria-label="Use jobs_ch"></td>
                  <td class="source-name">jobs_ch</td>
                  <td>runtime/jobs_ch/main-config/jobs_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="parser_source" value="jobscout24_ch" checked aria-label="Use jobscout24_ch"></td>
                  <td class="source-name">jobscout24_ch</td>
                  <td>runtime/jobscout24_ch/main-config/jobscout24_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="parser_source" value="jobup_ch" checked aria-label="Use jobup_ch"></td>
                  <td class="source-name">jobup_ch</td>
                  <td>runtime/jobup_ch/main-config/jobup_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="parser_source" value="linked_in" checked aria-label="Use linked_in"></td>
                  <td class="source-name">linked_in</td>
                  <td>runtime/linked_in/main-config/linked_in.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="parser_source" value="swissdevjobs_ch" checked aria-label="Use swissdevjobs_ch"></td>
                  <td class="source-name">swissdevjobs_ch</td>
                  <td>runtime/swissdevjobs_ch/main-config/swissdevjobs_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
              </tbody>
            </table>
            <div class="row">
              <div class="field">
                <label for="parser_mode">Mode</label>
                <select id="parser_mode" name="parser_mode">
                  <option>search</option>
                  <option>new</option>
                </select>
              </div>
              <div class="field">
                <label for="parser_canton">Canton</label>
                <input id="parser_canton" name="parser_canton" placeholder="zh">
              </div>
            </div>
            <div class="row">
              <div class="field">
                <label for="parser_term">Search term</label>
                <input id="parser_term" name="parser_term" placeholder="python">
              </div>
              <div class="field">
                <label for="parser_location">Location</label>
                <input id="parser_location" name="parser_location" placeholder="zurich">
              </div>
            </div>
            <div class="row">
              <div class="field">
                <label for="parser_pages">Max pages</label>
                <input id="parser_pages" name="parser_pages" type="number" min="1" placeholder="Optional">
              </div>
              <div class="field">
                <label for="parser_detail_limit">Detail limit</label>
                <input id="parser_detail_limit" name="parser_detail_limit" type="number" min="0" placeholder="Optional">
              </div>
            </div>
            <div class="actions">
              <button class="btn primary" type="button" title="Run selected vacancy parsers">Run Parser</button>
              <button class="btn secondary" type="button" title="Preview command shell">Preview Command</button>
            </div>
          </form>
          <article class="parser-panel" aria-label="Collection run preview">
            <h2>Run Preview</h2>
            <p>This panel will show parser status, progress, and database write results when collection is connected.</p>
            <div class="parser-preview">
              <div class="parser-step">
                <span class="step-index">1</span>
                <span><strong class="step-title">Prepare query</strong>Validate source, terms, location, and pagination limits.</span>
              </div>
              <div class="parser-step">
                <span class="step-index">2</span>
                <span><strong class="step-title">Collect vacancies</strong>Run provider parsing and detail-page enrichment.</span>
              </div>
              <div class="parser-step">
                <span class="step-index">3</span>
                <span><strong class="step-title">Update database</strong>Persist new vacancies into the selected local SQLite database.</span>
              </div>
            </div>
          </article>
        </section>
      </section>
      <section class="workspace-panel" id="ai-analyse-workspace" hidden>
        <div class="toolbar">
          <div>
            <p class="section-kicker">AI Analyse</p>
            <h1>Analyse New Vacancies</h1>
            <p class="sub">Visual shell for enriching fresh local vacancies with AI role, skill, salary, and seniority signals.</p>
          </div>
        </div>
        <section class="parser-grid" aria-label="AI vacancy analysis launcher">
          <form class="parser-panel" autocomplete="off">
            <h2>Analysis Parameters</h2>
            <p>Select vacancy sources, freshness scope, and model settings for a future AI analysis run.</p>
            <table class="source-table" aria-label="AI analysis sources">
              <thead>
                <tr>
                  <th scope="col">Use</th>
                  <th scope="col">Source</th>
                  <th scope="col">Database</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><input class="source-check" type="checkbox" name="analysis_source" value="jobs_ch" checked aria-label="Analyse jobs_ch"></td>
                  <td class="source-name">jobs_ch</td>
                  <td>runtime/jobs_ch/main-config/jobs_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="analysis_source" value="jobscout24_ch" checked aria-label="Analyse jobscout24_ch"></td>
                  <td class="source-name">jobscout24_ch</td>
                  <td>runtime/jobscout24_ch/main-config/jobscout24_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="analysis_source" value="jobup_ch" checked aria-label="Analyse jobup_ch"></td>
                  <td class="source-name">jobup_ch</td>
                  <td>runtime/jobup_ch/main-config/jobup_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="analysis_source" value="linked_in" checked aria-label="Analyse linked_in"></td>
                  <td class="source-name">linked_in</td>
                  <td>runtime/linked_in/main-config/linked_in.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="analysis_source" value="swissdevjobs_ch" checked aria-label="Analyse swissdevjobs_ch"></td>
                  <td class="source-name">swissdevjobs_ch</td>
                  <td>runtime/swissdevjobs_ch/main-config/swissdevjobs_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
              </tbody>
            </table>
            <div class="row">
              <div class="field">
                <label for="analysis_scope">Vacancy scope</label>
                <select id="analysis_scope" name="analysis_scope">
                  <option>new vacancies only</option>
                  <option>missing AI analysis</option>
                  <option>all selected vacancies</option>
                </select>
              </div>
              <div class="field">
                <label for="analysis_model">Model</label>
                <select id="analysis_model" name="analysis_model">
                  <option value="gpt-5-nano" selected>gpt-5-nano</option>
                  <option value="gpt-5-mini">gpt-5-mini</option>
                  <option value="gpt-4.1-nano">gpt-4.1-nano</option>
                  <option value="gpt-4.1-mini">gpt-4.1-mini</option>
                  <option value="o4-mini">o4-mini</option>
                </select>
              </div>
            </div>
            <div class="row">
              <div class="field">
                <label for="analysis_date_from">First seen from</label>
                <input id="analysis_date_from" name="analysis_date_from" type="text" inputmode="numeric" pattern="\\d{2}\\.\\d{2}\\.\\d{4}" placeholder="dd.mm.yyyy">
              </div>
              <div class="field">
                <label for="analysis_date_to">First seen to</label>
                <input id="analysis_date_to" name="analysis_date_to" type="text" inputmode="numeric" pattern="\\d{2}\\.\\d{2}\\.\\d{4}" placeholder="dd.mm.yyyy">
              </div>
            </div>
            <div class="row">
              <div class="field">
                <label for="analysis_limit">Vacancy limit</label>
                <input id="analysis_limit" name="analysis_limit" type="number" min="1" placeholder="Optional">
              </div>
              <div class="field">
                <label for="analysis_batch_size">Batch size</label>
                <input id="analysis_batch_size" name="analysis_batch_size" type="number" min="1" placeholder="25">
              </div>
            </div>
            <div class="field">
              <label for="analysis_notes">Analysis focus</label>
              <textarea id="analysis_notes" name="analysis_notes" placeholder="skills, role category, seniority, salary signals"></textarea>
            </div>
            <div class="actions">
              <button class="btn primary" type="button" title="Run selected AI analysis">Run AI Analyse</button>
              <button class="btn secondary" type="button" title="Preview analysis command shell">Preview Command</button>
            </div>
          </form>
          <article class="parser-panel" aria-label="AI analysis run preview">
            <h2>Run Preview</h2>
            <p>This panel will show AI analysis status, model usage, and database update results when enrichment is connected.</p>
            <div class="parser-preview">
              <div class="parser-step">
                <span class="step-index">1</span>
                <span><strong class="step-title">Find fresh vacancies</strong>Filter selected databases by first-seen date and missing AI analysis fields.</span>
              </div>
              <div class="parser-step">
                <span class="step-index">2</span>
                <span><strong class="step-title">Run AI enrichment</strong>Analyse vacancy descriptions for role category, seniority, skills, and salary signals.</span>
              </div>
              <div class="parser-step">
                <span class="step-index">3</span>
                <span><strong class="step-title">Write analysis results</strong>Persist structured AI output back into the selected local SQLite databases.</span>
              </div>
            </div>
          </article>
        </section>
      </section>
      <section class="workspace-panel" id="resume-matcher-workspace" hidden>
        <div class="toolbar resume-toolbar">
          <div>
            <p class="section-kicker">Resume matcher</p>
            <h1>Tailor Resume To Vacancy</h1>
            <p class="sub">Paste a vacancy URL and your current resume to generate a focused draft and keyword gap review.</p>
          </div>
          <div class="resume-status-cards" aria-label="Resume matcher configuration">
            <div class="resume-status-card">
              <span class="resume-status-icon" aria-hidden="true">✦</span>
              <span><strong>AI Model</strong><span>Local keyword analysis</span></span>
            </div>
            <div class="resume-status-card">
              <span class="resume-status-icon" aria-hidden="true">◉</span>
              <span><strong>Database</strong><span>Local + Live Web</span></span>
            </div>
          </div>
        </div>
        <section class="resume-grid" aria-label="Resume matcher">
          <form class="resume-form" id="resume-match-form" autocomplete="off">
            <div class="resume-input-cards">
              <article class="resume-panel resume-card">
                <h2>1. Vacancy Source</h2>
                <p>Choose where to get the vacancy from</p>
                <div class="resume-segment" aria-label="Vacancy source mode">
                  <button class="is-active" type="button">⌁ URL Link</button>
                  <button type="button">▤ Local Database</button>
                  <button type="button">▧ Paste Text</button>
                </div>
                <div class="resume-input-grid">
                  <div class="field">
                    <label for="vacancy_url">Vacancy URL</label>
                    <div class="resume-url-row">
                      <input id="vacancy_url" name="vacancy_url" type="url" placeholder="https://www.jobs.ch/...">
                      <button class="details-toggle" type="submit" title="Fetch vacancy and generate match">Fetch Vacancy</button>
                    </div>
                    <span class="resume-inline-status is-muted" id="resume-vacancy-load-status">Waiting for vacancy</span>
                  </div>
                  <div class="field">
                    <label for="target_title">Target title override <span>(optional)</span></label>
                    <input id="target_title" name="target_title" placeholder="e.g. Senior Software Engineer">
                  </div>
                  <div class="field">
                    <label for="job_description">Vacancy description fallback</label>
                    <textarea id="job_description" name="job_description" placeholder="Paste the vacancy text here if the site blocks automatic reading."></textarea>
                  </div>
                </div>
              </article>
              <article class="resume-panel resume-card">
                <h2>2. Your Current Resume</h2>
                <p>Upload your resume or paste your current resume text</p>
                <div class="resume-segment" aria-label="Resume input mode">
                  <button class="is-active" type="button">↥ Upload File</button>
                  <button type="button">♢ Paste Text</button>
                  <button type="button">▣ Review</button>
                </div>
                <div class="resume-file-zone">
                  <input class="resume-file-input" id="resume_pdf" name="resume_pdf" type="file" accept="application/pdf">
                  <label class="resume-upload-label" for="resume_pdf">↥ Upload File</label>
                  <div class="resume-file-row">
                    <div>
                      <p class="resume-file-name" id="resume-file-name">No PDF selected</p>
                      <span class="resume-file-hint">PDF resume or pasted text below</span>
                    </div>
                    <button class="details-toggle" type="button" id="resume-clear-file" title="Remove attached PDF">Remove</button>
                  </div>
                  <div class="resume-drop-hint">or drag and drop your file here<br>Supports: PDF (Max 10MB)</div>
                </div>
                <div class="field">
                  <label for="resume_text">Paste resume text</label>
                  <textarea id="resume_text" name="resume_text" placeholder="Paste your current resume text here."></textarea>
                </div>
              </article>
            </div>
            <section class="resume-panel resume-preview-panel">
              <div class="resume-preview-head">
                <div>
                  <h2>3. Vacancy Preview</h2>
                  <p>Extracted from the source</p>
                </div>
              </div>
              <article class="resume-vacancy-preview" id="resume-vacancy-preview">
                <h3>No vacancy loaded yet</h3>
                <div class="resume-preview-tags">
                  <span class="tag">Waiting</span>
                </div>
                <p>Paste a vacancy URL or fallback description, then run the matcher to preview the vacancy context used for the analysis.</p>
              </article>
              <div class="actions resume-action-row">
                <button class="btn primary" type="submit" title="Generate resume match">✦ Analyse &amp; Generate Match</button>
                <button class="btn secondary" type="button" id="resume-reset" title="Clear resume matcher">Clear All</button>
              </div>
            </section>
          </form>
          <article class="resume-output" aria-label="Resume match result">
            <section class="resume-panel">
              <h2>4. Match Analysis</h2>
              <p class="resume-note" id="resume-match-status">No resume match generated yet.</p>
              <div class="resume-analysis-grid">
                <section class="resume-report-section">
                  <div class="resume-score" id="resume-score-card" hidden>
                    <span class="resume-score-value" id="resume-score-value">0%</span>
                    <div>
                      <h2 id="resume-vacancy-title">Vacancy match</h2>
                      <p id="resume-vacancy-meta">Waiting for input.</p>
                    </div>
                  </div>
                  <div class="resume-metric-list" aria-label="Match score breakdown">
                    <div class="resume-metric">
                      <div class="resume-metric-row"><span>Skills Match</span><span id="resume-skills-score">0%</span></div>
                      <div class="resume-meter"><span id="resume-skills-meter" style="width: 0%"></span></div>
                    </div>
                    <div class="resume-metric">
                      <div class="resume-metric-row"><span>Experience Match</span><span id="resume-experience-score">0%</span></div>
                      <div class="resume-meter is-warm"><span id="resume-experience-meter" style="width: 0%"></span></div>
                    </div>
                    <div class="resume-metric">
                      <div class="resume-metric-row"><span>Keywords Match</span><span id="resume-keywords-score">0%</span></div>
                      <div class="resume-meter"><span id="resume-keywords-meter" style="width: 0%"></span></div>
                    </div>
                  </div>
                </section>
                <section class="resume-report-section resume-keyword-columns">
                  <div>
                    <p class="summary-title">Key Strengths</p>
                    <div class="keyword-cloud" id="resume-matched-keywords"></div>
                  </div>
                  <div>
                    <p class="summary-title">Missing Keywords</p>
                    <div class="keyword-cloud" id="resume-missing-keywords"></div>
                  </div>
                </section>
                <section class="resume-report-section">
                  <p class="summary-title">Recommendations</p>
                  <div class="resume-recommendation-list" id="resume-recommendations">
                    <div class="empty">Run the matcher to see recommendations.</div>
                  </div>
                </section>
              </div>
            </section>
            <section class="resume-panel">
              <div class="resume-result-head">
                <div>
                  <h2>5. Tailored Resume Output</h2>
                  <p>Your optimized resume ready to download</p>
                </div>
              </div>
              <div class="resume-output-grid">
                <div>
                  <p class="summary-title">Preview (First 500 characters)</p>
                  <textarea class="resume-result-text" id="resume_result" readonly placeholder="Generated draft will appear here."></textarea>
                </div>
                <div>
                  <p class="summary-title">Download Files</p>
                  <div class="resume-download-grid">
                    <button class="resume-copy-card" type="button" id="resume-copy" title="Copy tailored resume draft">
                      <span class="resume-download-icon" aria-hidden="true">TXT</span>
                      <span>Copy Draft<small>Generated resume text</small></span>
                    </button>
                    <a class="resume-download-card" id="resume-download-pdf" href="#" download="tailored-resume.pdf" hidden>
                      <span class="resume-download-icon" aria-hidden="true">PDF</span>
                      <span>Download PDF<small>Portable Document Format</small></span>
                    </a>
                  </div>
                </div>
              </div>
              <div class="resume-tip">Tip: Review the recommendations above and customize the generated resume to better highlight your most relevant achievements.</div>
            </section>
          </article>
        </section>
      </section>
      <section class="workspace-panel" id="public-stats-workspace" hidden>
        <div class="toolbar">
          <div>
            <p class="section-kicker">Public Stats</p>
            <h1>Create Public Snapshot</h1>
            <p class="sub">Visual shell for building anonymized public statistics snapshots from local vacancy databases.</p>
          </div>
        </div>
        <section class="parser-grid" aria-label="Public statistics snapshot builder">
          <form class="parser-panel" autocomplete="off">
            <h2>Snapshot Parameters</h2>
            <p>Select the source databases and output targets for a future public statistics build.</p>
            <table class="source-table" aria-label="Public statistics sources">
              <thead>
                <tr>
                  <th scope="col">Use</th>
                  <th scope="col">Source</th>
                  <th scope="col">Database</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><input class="source-check" type="checkbox" name="stats_source" value="jobs_ch" checked aria-label="Use jobs_ch statistics"></td>
                  <td class="source-name">jobs_ch</td>
                  <td>runtime/jobs_ch/main-config/jobs_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="stats_source" value="jobscout24_ch" checked aria-label="Use jobscout24_ch statistics"></td>
                  <td class="source-name">jobscout24_ch</td>
                  <td>runtime/jobscout24_ch/main-config/jobscout24_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="stats_source" value="jobup_ch" checked aria-label="Use jobup_ch statistics"></td>
                  <td class="source-name">jobup_ch</td>
                  <td>runtime/jobup_ch/main-config/jobup_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="stats_source" value="linked_in" checked aria-label="Use linked_in statistics"></td>
                  <td class="source-name">linked_in</td>
                  <td>runtime/linked_in/main-config/linked_in.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
                <tr>
                  <td><input class="source-check" type="checkbox" name="stats_source" value="swissdevjobs_ch" checked aria-label="Use swissdevjobs_ch statistics"></td>
                  <td class="source-name">swissdevjobs_ch</td>
                  <td>runtime/swissdevjobs_ch/main-config/swissdevjobs_ch.sqlite</td>
                  <td><span class="source-status">Ready</span></td>
                </tr>
              </tbody>
            </table>
            <div class="row">
              <div class="field">
                <label for="stats_snapshot_date">Snapshot date</label>
                <input id="stats_snapshot_date" name="stats_snapshot_date" type="text" inputmode="numeric" pattern="\\d{2}\\.\\d{2}\\.\\d{4}" placeholder="dd.mm.yyyy">
              </div>
              <div class="field">
                <label for="stats_min_salary_count">Salary group minimum</label>
                <input id="stats_min_salary_count" name="stats_min_salary_count" type="number" min="1" placeholder="10">
              </div>
            </div>
            <div class="row">
              <div class="field">
                <label for="stats_output_dir">Output directory</label>
                <input id="stats_output_dir" name="stats_output_dir" placeholder="public_stats">
              </div>
              <div class="field">
                <label for="stats_site_dir">Site data directory</label>
                <input id="stats_site_dir" name="stats_site_dir" placeholder="site/public">
              </div>
            </div>
            <div class="settings-row">
              <div class="setting-toggle">
                <span>Generate JSON snapshot</span>
                <span class="switch is-on" aria-hidden="true"></span>
              </div>
              <div class="setting-toggle">
                <span>Generate CSV exports</span>
                <span class="switch is-on" aria-hidden="true"></span>
              </div>
              <div class="setting-toggle">
                <span>Sync website data</span>
                <span class="switch is-on" aria-hidden="true"></span>
              </div>
            </div>
            <div class="actions">
              <button class="btn primary" type="button" title="Build public statistics snapshot">Build Snapshot</button>
              <button class="btn secondary" type="button" title="Preview public statistics command shell">Preview Command</button>
            </div>
          </form>
          <article class="parser-panel" aria-label="Public snapshot run preview">
            <h2>Run Preview</h2>
            <p>This panel will show snapshot generation status, exported file counts, and website sync results when the builder is connected.</p>
            <div class="parser-preview">
              <div class="parser-step">
                <span class="step-index">1</span>
                <span><strong class="step-title">Load vacancy data</strong>Read selected local SQLite databases and merge provider datasets.</span>
              </div>
              <div class="parser-step">
                <span class="step-index">2</span>
                <span><strong class="step-title">Build statistics</strong>Aggregate market overview, trends, salary groups, roles, locations, and skills.</span>
              </div>
              <div class="parser-step">
                <span class="step-index">3</span>
                <span><strong class="step-title">Publish snapshot</strong>Write anonymized JSON and CSV files for the public analytics site.</span>
              </div>
            </div>
          </article>
        </section>
      </section>
      <section class="workspace-panel" id="settings-workspace" hidden>
        <div class="toolbar">
          <div>
            <p class="section-kicker">Settings</p>
            <h1>Application Settings</h1>
            <p class="sub">Visual placeholder for future source management, data collection, and statistics export controls.</p>
          </div>
        </div>
        <section class="settings-grid" aria-label="Application settings">
          <article class="settings-panel">
            <h2>Vacancy Sources</h2>
            <p>Connect and select local databases for browsing, search, and future synchronization.</p>
            <div class="settings-row">
              <div class="setting-toggle">
                <span>Use main-config databases</span>
                <span class="switch is-on" aria-hidden="true"></span>
              </div>
              <div class="setting-toggle">
                <span>Show test databases</span>
                <span class="switch" aria-hidden="true"></span>
              </div>
            </div>
          </article>
          <article class="settings-panel">
            <h2>Statistics Builder</h2>
            <p>Reserved for running public statistics generation separately from vacancy browsing.</p>
            <div class="settings-row">
              <div class="setting-toggle">
                <span>Update public CSV files</span>
                <span class="switch is-on" aria-hidden="true"></span>
              </div>
              <div class="setting-toggle">
                <span>Save JSON snapshots</span>
                <span class="switch is-on" aria-hidden="true"></span>
              </div>
            </div>
          </article>
          <article class="settings-panel">
            <h2>Interface</h2>
            <p>Display settings for results, vacancy cards, and local helper content.</p>
            <div class="settings-row">
              <div class="setting-toggle">
                <span>Compact vacancy cards</span>
                <span class="switch" aria-hidden="true"></span>
              </div>
              <div class="setting-toggle">
                <span>Show JSON details</span>
                <span class="switch" aria-hidden="true"></span>
              </div>
            </div>
          </article>
        </section>
      </section>
    </main>
  </div>
  <aside class="log-drawer" id="log-drawer" aria-label="Application logs" aria-hidden="true">
    <button class="log-toggle" id="log-toggle" type="button" aria-controls="log-drawer" aria-expanded="false" title="Open application logs">☰</button>
    <div class="log-head">
      <div>
        <p class="log-title">Application Logs</p>
        <p class="log-subtitle">Search, collection, AI analysis, and public snapshot events.</p>
      </div>
      <button class="log-close" id="log-close" type="button" aria-label="Close logs">×</button>
    </div>
    <div class="log-list" id="log-list" role="log" aria-live="polite"></div>
    <div class="log-actions">
      <button class="log-clear" id="log-clear" type="button">Clear logs</button>
    </div>
  </aside>
  <script>
    const appEl = document.querySelector("#app");
    const menuButtons = Array.from(document.querySelectorAll("[data-view-target]"));
    const vacanciesWorkspaceEl = document.querySelector("#vacancies-workspace");
    const parserWorkspaceEl = document.querySelector("#parser-workspace");
    const aiAnalyseWorkspaceEl = document.querySelector("#ai-analyse-workspace");
    const resumeMatcherWorkspaceEl = document.querySelector("#resume-matcher-workspace");
    const publicStatsWorkspaceEl = document.querySelector("#public-stats-workspace");
    const settingsWorkspaceEl = document.querySelector("#settings-workspace");
    const resumeMatchFormEl = document.querySelector("#resume-match-form");
    const resumeResetEl = document.querySelector("#resume-reset");
    const resumeCopyEl = document.querySelector("#resume-copy");
    const resumePdfInputEl = document.querySelector("#resume_pdf");
    const resumeClearFileEl = document.querySelector("#resume-clear-file");
    const resumeFileNameEl = document.querySelector("#resume-file-name");
    const resumeDownloadPdfEl = document.querySelector("#resume-download-pdf");
    const resumeStatusEl = document.querySelector("#resume-match-status");
    const resumeVacancyLoadStatusEl = document.querySelector("#resume-vacancy-load-status");
    const resumeVacancyPreviewEl = document.querySelector("#resume-vacancy-preview");
    const resumeScoreCardEl = document.querySelector("#resume-score-card");
    const resumeScoreValueEl = document.querySelector("#resume-score-value");
    const resumeVacancyTitleEl = document.querySelector("#resume-vacancy-title");
    const resumeVacancyMetaEl = document.querySelector("#resume-vacancy-meta");
    const resumeSkillsScoreEl = document.querySelector("#resume-skills-score");
    const resumeExperienceScoreEl = document.querySelector("#resume-experience-score");
    const resumeKeywordsScoreEl = document.querySelector("#resume-keywords-score");
    const resumeSkillsMeterEl = document.querySelector("#resume-skills-meter");
    const resumeExperienceMeterEl = document.querySelector("#resume-experience-meter");
    const resumeKeywordsMeterEl = document.querySelector("#resume-keywords-meter");
    const resumeMatchedKeywordsEl = document.querySelector("#resume-matched-keywords");
    const resumeMissingKeywordsEl = document.querySelector("#resume-missing-keywords");
    const resumeRecommendationsEl = document.querySelector("#resume-recommendations");
    const resumeResultEl = document.querySelector("#resume_result");
    const logToggleEl = document.querySelector("#log-toggle");
    const logDrawerEl = document.querySelector("#log-drawer");
    const logCloseEl = document.querySelector("#log-close");
    const logListEl = document.querySelector("#log-list");
    const logClearEl = document.querySelector("#log-clear");
    const workspaceKickerEl = document.querySelector("#workspace-kicker");
    const form = document.querySelector("#search-form");
    const resultsEl = document.querySelector("#results");
    const errorsEl = document.querySelector("#errors");
    const databaseSummaryEl = document.querySelector("#database-summary");
    const paginationEl = document.querySelector("#pagination");
    const subtitleEl = document.querySelector("#subtitle");
    const resetBtn = document.querySelector("#reset");
    const resultTitleEl = document.querySelector("#result-title");
    const salaryMinInput = document.querySelector("#salary_min");
    const salaryMaxInput = document.querySelector("#salary_max");
    const salaryMinRange = document.querySelector("#salary_min_range");
    const salaryMaxRange = document.querySelector("#salary_max_range");
    const salaryMinText = document.querySelector("#salary_min_text");
    const salaryMaxText = document.querySelector("#salary_max_text");
    const salaryTrack = document.querySelector("#salary-track");
    const salaryRangeMax = Number(salaryMaxRange.max);
    const pageSize = 10;
    const maxLogEntries = 80;
    const logs = [];
    const parserRunState = {
      runId: "",
      lastSeq: 0,
      timer: 0,
      status: "idle",
    };
    const aiAnalysisRunState = {
      runId: "",
      lastSeq: 0,
      timer: 0,
      status: "idle",
    };
    const publicStatsRunState = {
      runId: "",
      lastSeq: 0,
      timer: 0,
      status: "idle",
    };
    let currentPage = 1;
    let currentView = "vacancies";
    let resumePdfObjectUrl = "";

    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
    const formatChf = (value) => `${Number(value).toLocaleString("en-US")} CHF`;
    const viewLabels = {
      vacancies: "Vacancy Browser",
      search: "Vacancy Search",
      "ai-analyse": "AI Analyse",
      "resume-matcher": "Resume matcher",
      "public-stats": "Public Stats",
      settings: "Settings",
    };

    function formatLogTime(date) {
      return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    function renderLogs() {
      if (!logs.length) {
        logListEl.innerHTML = '<div class="empty">No log entries yet.</div>';
        return;
      }
      logListEl.innerHTML = logs.map((entry) => `
        <article class="log-entry is-${esc(entry.level)}">
          <div class="log-entry-head">
            <span class="log-entry-title">${esc(entry.title)}</span>
            <span class="log-entry-time">${esc(entry.time)}</span>
          </div>
          <p class="log-entry-message">${esc(entry.message)}</p>
        </article>
      `).join("");
      logListEl.scrollTop = 0;
    }

    function addLog(title, message, level = "info") {
      logs.unshift({ title, message, level, time: formatLogTime(new Date()) });
      if (logs.length > maxLogEntries) logs.length = maxLogEntries;
      renderLogs();
    }

    function setLogDrawer(open) {
      logDrawerEl.classList.toggle("is-open", open);
      logDrawerEl.setAttribute("aria-hidden", String(!open));
      logToggleEl.setAttribute("aria-expanded", String(open));
    }

    function parserLogTitle(entry) {
      const source = entry.source ? ` ${entry.source}` : "";
      const stream = entry.stream && entry.stream !== "system" ? ` ${entry.stream}` : "";
      return `Parser${source}${stream}`;
    }

    function ingestParserLogs(payload) {
      for (const entry of payload.logs || []) {
        parserRunState.lastSeq = Math.max(parserRunState.lastSeq, Number(entry.seq || 0));
        addLog(parserLogTitle(entry), entry.message || "", entry.level || "info");
      }
      parserRunState.status = payload.status || parserRunState.status;
    }

    async function pollParserRun() {
      if (!parserRunState.runId) return;
      try {
        const params = new URLSearchParams({
          run_id: parserRunState.runId,
          after: String(parserRunState.lastSeq),
        });
        const response = await fetch(`/api/parser-runs?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) {
          addLog("Parser", payload.error || "Failed to read parser logs.", "error");
          window.clearInterval(parserRunState.timer);
          parserRunState.timer = 0;
          return;
        }
        ingestParserLogs(payload);
        if (["completed", "failed"].includes(payload.status)) {
          window.clearInterval(parserRunState.timer);
          parserRunState.timer = 0;
          parserRunState.runId = "";
          loadFacets().then(() => runSearch(1)).catch((error) => {
            addLog("Vacancy Search", error.message || String(error), "error");
          });
        }
      } catch (error) {
        addLog("Parser", error.message || String(error), "error");
        window.clearInterval(parserRunState.timer);
        parserRunState.timer = 0;
      }
    }

    function collectParserPayload() {
      const sources = Array.from(document.querySelectorAll('input[name="parser_source"]:checked'))
        .map((input) => input.value);
      return {
        sources,
        mode: document.querySelector("#parser_mode")?.value || "new",
        canton: document.querySelector("#parser_canton")?.value || "",
        term: document.querySelector("#parser_term")?.value || "",
        location: document.querySelector("#parser_location")?.value || "",
        max_pages: document.querySelector("#parser_pages")?.value || "",
        detail_limit: document.querySelector("#parser_detail_limit")?.value || "",
      };
    }

    async function startParserRun() {
      if (parserRunState.timer) {
        addLog("Vacancy Collection", "Parser run is already active.", "warning");
        setLogDrawer(true);
        return;
      }
      const payload = collectParserPayload();
      if (!payload.sources.length) {
        addLog("Vacancy Collection", "Select at least one parser source.", "error");
        setLogDrawer(true);
        return;
      }
      addLog("Vacancy Collection", `Starting parser run for ${payload.sources.join(", ")}.`);
      setLogDrawer(true);
      try {
        const response = await fetch("/api/parser-runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          addLog("Vacancy Collection", data.error || "Failed to start parser run.", "error");
          return;
        }
        parserRunState.runId = data.id;
        parserRunState.lastSeq = 0;
        parserRunState.status = data.status;
        ingestParserLogs(data);
        parserRunState.timer = window.setInterval(pollParserRun, 1000);
        pollParserRun();
      } catch (error) {
        addLog("Vacancy Collection", error.message || String(error), "error");
      }
    }

    function aiAnalysisLogTitle(entry) {
      const source = entry.source ? ` ${entry.source}` : "";
      const stream = entry.stream && entry.stream !== "system" ? ` ${entry.stream}` : "";
      return `AI Analyse${source}${stream}`;
    }

    function ingestAiAnalysisLogs(payload) {
      for (const entry of payload.logs || []) {
        aiAnalysisRunState.lastSeq = Math.max(aiAnalysisRunState.lastSeq, Number(entry.seq || 0));
        addLog(aiAnalysisLogTitle(entry), entry.message || "", entry.level || "info");
      }
      aiAnalysisRunState.status = payload.status || aiAnalysisRunState.status;
    }

    async function pollAiAnalysisRun() {
      if (!aiAnalysisRunState.runId) return;
      try {
        const params = new URLSearchParams({
          run_id: aiAnalysisRunState.runId,
          after: String(aiAnalysisRunState.lastSeq),
        });
        const response = await fetch(`/api/ai-analysis-runs?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) {
          addLog("AI Analyse", payload.error || "Failed to read AI analysis logs.", "error");
          window.clearInterval(aiAnalysisRunState.timer);
          aiAnalysisRunState.timer = 0;
          return;
        }
        ingestAiAnalysisLogs(payload);
        if (["completed", "failed"].includes(payload.status)) {
          window.clearInterval(aiAnalysisRunState.timer);
          aiAnalysisRunState.timer = 0;
          aiAnalysisRunState.runId = "";
          loadFacets().then(() => runSearch(1)).catch((error) => {
            addLog("Vacancy Search", error.message || String(error), "error");
          });
        }
      } catch (error) {
        addLog("AI Analyse", error.message || String(error), "error");
        window.clearInterval(aiAnalysisRunState.timer);
        aiAnalysisRunState.timer = 0;
      }
    }

    function collectAiAnalysisPayload() {
      const sources = Array.from(document.querySelectorAll('input[name="analysis_source"]:checked'))
        .map((input) => input.value);
      return {
        sources,
        scope: document.querySelector("#analysis_scope")?.value || "new vacancies only",
        model: document.querySelector("#analysis_model")?.value || "gpt-5-nano",
        first_seen_from: document.querySelector("#analysis_date_from")?.value || "",
        first_seen_to: document.querySelector("#analysis_date_to")?.value || "",
        limit: document.querySelector("#analysis_limit")?.value || "",
      };
    }

    async function startAiAnalysisRun() {
      if (aiAnalysisRunState.timer) {
        addLog("AI Analyse", "AI analysis run is already active.", "warning");
        setLogDrawer(true);
        return;
      }
      const payload = collectAiAnalysisPayload();
      if (!payload.sources.length) {
        addLog("AI Analyse", "Select at least one AI analysis source.", "error");
        setLogDrawer(true);
        return;
      }
      addLog("AI Analyse", `Starting AI analysis for ${payload.sources.join(", ")} with ${payload.model}.`);
      setLogDrawer(true);
      try {
        const response = await fetch("/api/ai-analysis-runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          addLog("AI Analyse", data.error || "Failed to start AI analysis run.", "error");
          return;
        }
        aiAnalysisRunState.runId = data.id;
        aiAnalysisRunState.lastSeq = 0;
        aiAnalysisRunState.status = data.status;
        ingestAiAnalysisLogs(data);
        aiAnalysisRunState.timer = window.setInterval(pollAiAnalysisRun, 1000);
        pollAiAnalysisRun();
      } catch (error) {
        addLog("AI Analyse", error.message || String(error), "error");
      }
    }

    function publicStatsLogTitle(entry) {
      const stage = entry.source ? ` ${entry.source}` : "";
      const stream = entry.stream && entry.stream !== "system" ? ` ${entry.stream}` : "";
      return `Public Stats${stage}${stream}`;
    }

    function ingestPublicStatsLogs(payload) {
      for (const entry of payload.logs || []) {
        publicStatsRunState.lastSeq = Math.max(publicStatsRunState.lastSeq, Number(entry.seq || 0));
        addLog(publicStatsLogTitle(entry), entry.message || "", entry.level || "info");
      }
      publicStatsRunState.status = payload.status || publicStatsRunState.status;
    }

    async function pollPublicStatsRun() {
      if (!publicStatsRunState.runId) return;
      try {
        const params = new URLSearchParams({
          run_id: publicStatsRunState.runId,
          after: String(publicStatsRunState.lastSeq),
        });
        const response = await fetch(`/api/public-stats-runs?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) {
          addLog("Public Stats", payload.error || "Failed to read public stats logs.", "error");
          window.clearInterval(publicStatsRunState.timer);
          publicStatsRunState.timer = 0;
          return;
        }
        ingestPublicStatsLogs(payload);
        if (["completed", "failed"].includes(payload.status)) {
          window.clearInterval(publicStatsRunState.timer);
          publicStatsRunState.timer = 0;
          publicStatsRunState.runId = "";
        }
      } catch (error) {
        addLog("Public Stats", error.message || String(error), "error");
        window.clearInterval(publicStatsRunState.timer);
        publicStatsRunState.timer = 0;
      }
    }

    function collectPublicStatsPayload() {
      const sources = Array.from(document.querySelectorAll('input[name="stats_source"]:checked'))
        .map((input) => input.value);
      return {
        sources,
        snapshot_date: document.querySelector("#stats_snapshot_date")?.value || "",
        salary_group_minimum: document.querySelector("#stats_min_salary_count")?.value || "",
        output_dir: document.querySelector("#stats_output_dir")?.value || "public_stats",
        site_dir: document.querySelector("#stats_site_dir")?.value || "site/public",
        sync_site: true,
      };
    }

    async function startPublicStatsRun() {
      if (publicStatsRunState.timer) {
        addLog("Public Stats", "Public stats build is already active.", "warning");
        setLogDrawer(true);
        return;
      }
      const payload = collectPublicStatsPayload();
      if (!payload.sources.length) {
        addLog("Public Stats", "Select at least one public stats source.", "error");
        setLogDrawer(true);
        return;
      }
      addLog("Public Stats", `Starting public stats build for ${payload.sources.join(", ")}.`);
      setLogDrawer(true);
      try {
        const response = await fetch("/api/public-stats-runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          addLog("Public Stats", data.error || "Failed to start public stats build.", "error");
          return;
        }
        publicStatsRunState.runId = data.id;
        publicStatsRunState.lastSeq = 0;
        publicStatsRunState.status = data.status;
        ingestPublicStatsLogs(data);
        publicStatsRunState.timer = window.setInterval(pollPublicStatsRun, 1000);
        pollPublicStatsRun();
      } catch (error) {
        addLog("Public Stats", error.message || String(error), "error");
      }
    }

    function syncSalaryTrack() {
      const min = Number(salaryMinRange.value);
      const max = Number(salaryMaxRange.value);
      const left = (min / salaryRangeMax) * 100;
      const right = (max / salaryRangeMax) * 100;
      salaryTrack.style.background = `linear-gradient(90deg, #e5e7eb 0%, #e5e7eb ${left}%, var(--accent) ${left}%, var(--accent) ${right}%, #e5e7eb ${right}%, #e5e7eb 100%)`;
      salaryMinText.textContent = min > 0 ? formatChf(min) : "Any min";
      salaryMaxText.textContent = max < salaryRangeMax ? formatChf(max) : "Any max";
    }

    function syncSalaryInputsFromRange(changed) {
      let min = Number(salaryMinRange.value);
      let max = Number(salaryMaxRange.value);
      if (min > max) {
        if (changed === "min") {
          max = min;
          salaryMaxRange.value = String(max);
        } else {
          min = max;
          salaryMinRange.value = String(min);
        }
      }
      salaryMinInput.value = min > 0 ? String(min) : "";
      salaryMaxInput.value = max < salaryRangeMax ? String(max) : "";
      syncSalaryTrack();
    }

    function syncSalaryRangeFromInputs() {
      const min = Math.max(0, Math.min(Number(salaryMinInput.value || 0), salaryRangeMax));
      const maxRaw = salaryMaxInput.value ? Number(salaryMaxInput.value) : salaryRangeMax;
      const max = Math.max(0, Math.min(maxRaw, salaryRangeMax));
      salaryMinRange.value = String(Math.min(min, max));
      salaryMaxRange.value = String(Math.max(min, max));
      syncSalaryTrack();
    }

    function setOptions(select, items) {
      const current = select.value;
      select.innerHTML = '<option value="">Any</option>' + items.map((item) => {
        const label = `${item.value} (${item.count})`;
        return `<option value="${esc(item.value)}">${esc(label)}</option>`;
      }).join("");
      select.value = current;
    }

    function setDatalist(id, items) {
      document.querySelector(id).innerHTML = items.map((item) =>
        `<option value="${esc(item.value)}"></option>`
      ).join("");
    }

    function mergeFacetItems(items) {
      const merged = new Map();
      for (const item of items) {
        const key = item.value;
        if (!key) continue;
        merged.set(key, (merged.get(key) || 0) + Number(item.count || 0));
      }
      return Array.from(merged.entries())
        .map(([value, count]) => ({ value, count }))
        .sort((left, right) => right.count - left.count || left.value.localeCompare(right.value));
    }

    function normalizeDateParam(key, value) {
      if (!["date_from", "date_to"].includes(key)) return value;
      const match = value.match(/^(\\d{2})\\.(\\d{2})\\.(\\d{4})$/);
      if (!match) return value;
      return `${match[3]}-${match[2]}-${match[1]}`;
    }

    function buildParams(page = currentPage) {
      const data = new FormData(form);
      const params = new URLSearchParams();
      for (const [key, value] of data.entries()) {
        const clean = String(value).trim();
        if (clean) params.set(key, normalizeDateParam(key, clean));
      }
      params.set("page", String(page));
      params.set("per_page", String(pageSize));
      return params;
    }

    function activateMenu(view) {
      for (const button of menuButtons) {
        const isActive = button.dataset.viewTarget === view;
        button.classList.toggle("is-active", isActive);
        if (isActive) {
          button.setAttribute("aria-current", "page");
        } else {
          button.removeAttribute("aria-current");
        }
      }
    }

    function setView(view, options = {}) {
      currentView = view;
      appEl.classList.remove("view-vacancies", "view-search", "view-ai-analyse", "view-resume-matcher", "view-public-stats", "view-settings");
      appEl.classList.add(`view-${view}`);
      activateMenu(view);

      const isParser = view === "search";
      const isAiAnalyse = view === "ai-analyse";
      const isResumeMatcher = view === "resume-matcher";
      const isPublicStats = view === "public-stats";
      const isSettings = view === "settings";
      vacanciesWorkspaceEl.hidden = isParser || isAiAnalyse || isResumeMatcher || isPublicStats || isSettings;
      parserWorkspaceEl.hidden = !isParser;
      aiAnalyseWorkspaceEl.hidden = !isAiAnalyse;
      resumeMatcherWorkspaceEl.hidden = !isResumeMatcher;
      publicStatsWorkspaceEl.hidden = !isPublicStats;
      settingsWorkspaceEl.hidden = !isSettings;

      if (view === "vacancies") {
        workspaceKickerEl.textContent = "Vacancy Browser";
        if (options.resetFilters) {
          form.reset();
          syncSalaryInputsFromRange();
          currentPage = 1;
          runSearch(1);
        }
        return;
      }

    }

    function renderErrors(errors) {
      if (!errors || !errors.length) {
        errorsEl.innerHTML = "";
        return;
      }
      errorsEl.innerHTML = `<div class="error">${esc(errors.length)} local database error(s). Check terminal output or database schema.</div>`;
    }

    function renderSummaryBlock(title, items) {
      if (!items || !items.length) return "";
      return `
        <div class="summary-block">
          <p class="summary-title">${esc(title)}</p>
          <div class="summary-list">
            ${items.map((item) => `
              <div class="summary-item">
                <span title="${esc(item.path || item.value || item.label)}">${esc(item.label || item.value)}</span>
                <span class="summary-count">${esc(item.count)}</span>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    function getVisiblePages(page, totalPages) {
      if (totalPages <= 7) {
        return Array.from({ length: totalPages }, (_, index) => index + 1);
      }
      const pages = new Set([1, totalPages, page - 1, page, page + 1]);
      if (page <= 3) {
        pages.add(2);
        pages.add(3);
        pages.add(4);
      }
      if (page >= totalPages - 2) {
        pages.add(totalPages - 3);
        pages.add(totalPages - 2);
        pages.add(totalPages - 1);
      }
      return [...pages]
        .filter((item) => item >= 1 && item <= totalPages)
        .sort((left, right) => left - right);
    }

    function renderPagination(payload) {
      const totalPages = Number(payload.total_pages || 1);
      const page = Number(payload.page || 1);
      if (totalPages <= 1) {
        paginationEl.innerHTML = "";
        return;
      }
      const pages = getVisiblePages(page, totalPages);
      const pageButtons = [];
      let previousPage = 0;
      for (const item of pages) {
        if (previousPage && item - previousPage > 1) {
          pageButtons.push('<span class="page-gap" aria-hidden="true">...</span>');
        }
        pageButtons.push(`
          <button class="page-btn ${item === page ? "is-active" : ""}" type="button" data-page="${item}" ${item === page ? 'aria-current="page"' : ""}>
            ${item}
          </button>
        `);
        previousPage = item;
      }
      paginationEl.innerHTML = `
        <button class="page-btn" type="button" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""} aria-label="Previous page">‹</button>
        ${pageButtons.join("")}
        <button class="page-btn" type="button" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""} aria-label="Next page">›</button>
      `;
    }

    function isPlainObject(value) {
      return value && typeof value === "object" && !Array.isArray(value);
    }

    function hasDetailValue(value) {
      if (value === null || value === undefined || value === "") return false;
      if (Array.isArray(value)) return value.length > 0;
      if (isPlainObject(value)) return Object.keys(value).length > 0;
      return true;
    }

    function formatDetailValue(value) {
      if (Array.isArray(value)) return value.join(", ");
      if (isPlainObject(value)) return JSON.stringify(value);
      if (typeof value === "boolean") return value ? "Yes" : "No";
      return String(value ?? "");
    }

    function makeDomId(prefix, value, index) {
      const clean = String(value || index).replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
      return `${prefix}-${clean || index}-${index}`;
    }

    function renderDetailGrid(rows) {
      const items = rows.filter(([, value]) => hasDetailValue(value));
      if (!items.length) return "";
      return `
        <div class="details-grid">
          ${items.map(([label, value]) => `
            <div class="detail-item">
              <span class="detail-label">${esc(label)}</span>
              <div class="detail-value">${esc(formatDetailValue(value))}</div>
            </div>
          `).join("")}
        </div>
      `;
    }

    function renderJsonSection(title, value) {
      if (!hasDetailValue(value)) return "";
      return `
        <section class="detail-section json-section" hidden>
          <h3 class="detail-section-title">${esc(title)}</h3>
          <pre class="detail-json">${esc(JSON.stringify(value, null, 2))}</pre>
        </section>
      `;
    }

    function renderJobDetails(job, detailsId) {
      const jsonSections = [
        renderJsonSection("Analytics", job.analytics),
        renderJsonSection("LLM analysis", job.llm_analysis),
        renderJsonSection("Job posting schema", job.job_posting_schema),
        renderJsonSection("Raw vacancy data", job.raw),
      ].filter(Boolean).join("");
      const rows = [
        ["Vacancy ID", job.id],
        ["Database", job.database],
        ["Source", job.source],
        ["URL", job.url],
        ["Company", job.company],
        ["Location", job.location],
        ["Employment type", job.employment_type],
        ["Role", job.role],
        ["Seniority", job.seniority],
        ["Detected seniority", job.detected_seniority],
        ["Remote mode", job.remote_mode],
        ["Salary", job.salary],
        ["Salary minimum", job.salary_min],
        ["Salary maximum", job.salary_max],
        ["Salary currency", job.salary_currency],
        ["Salary unit", job.salary_unit],
        ["Published", job.publication_date],
        ["First seen", job.first_seen_at],
        ["Last seen", job.last_seen_at],
        ["Detail skipped", job.detail_schema_skipped],
        ["Detail error", job.detail_schema_error],
        ["LLM model", job.llm_model],
        ["LLM analyzed at", job.llm_analyzed_at],
      ];
      return `
        <section class="job-details-panel" id="${detailsId}" hidden>
          ${renderDetailGrid(rows)}
          ${job.description_text ? `
            <section class="detail-section">
              <h3 class="detail-section-title">Description</h3>
              <p class="detail-description">${esc(job.description_text)}</p>
            </section>
          ` : ""}
          ${jsonSections ? `
            <button class="details-toggle json-toggle" type="button" aria-expanded="false" data-json-toggle>Show JSON</button>
            ${jsonSections}
          ` : ""}
        </section>
      `;
    }

    function renderResults(payload) {
      renderErrors(payload.database_errors);
      currentPage = Number(payload.page || 1);
      resultTitleEl.innerHTML = `Found <strong>${esc(payload.total ?? payload.count)}</strong> jobs`;
      renderPagination(payload);
      if (!payload.results.length) {
        resultsEl.innerHTML = '<div class="empty">No vacancies match these filters.</div>';
        return;
      }
      resultsEl.innerHTML = payload.results.map((job, index) => {
        const initial = String(job.company || job.title || "?").trim().slice(0, 1) || "?";
        const detailsId = makeDomId("job-details", job.id, index);
        const tags = [
          job.role ? `<span class="tag role">${esc(job.role)}</span>` : "",
          job.seniority ? `<span class="tag warn">${esc(job.seniority)}</span>` : "",
          job.remote_mode ? `<span class="tag">${esc(job.remote_mode)}</span>` : "",
          ...job.matched_keywords.map((keyword) => `<span class="tag keyword">${esc(keyword)}</span>`),
          ...job.skills.map((skill) => `<span class="tag">${esc(skill)}</span>`)
        ].filter(Boolean).join("");
        return `
          <article class="job">
            <div class="job-head">
              <div class="company-mark" aria-hidden="true">${esc(initial)}</div>
              <div>
                <h2>${esc(job.title || "Untitled vacancy")}</h2>
                <div class="company">${esc(job.company || "-")}</div>
                <div class="meta">
                  <span>${esc(job.location || "-")}</span>
                  <span>${esc(job.source || "-")}</span>
                  <span>${esc(job.publication_date || job.last_seen_at || "-")}</span>
                </div>
              </div>
              <div class="job-side">
                <div class="salary">${esc(job.salary || "")}</div>
                <div class="job-actions">
                  <button class="details-toggle" type="button" aria-expanded="false" aria-controls="${detailsId}" data-details-target="${detailsId}">Details</button>
                  ${job.url ? `<a class="open-link" href="${esc(job.url)}" target="_blank" rel="noreferrer" title="Open original vacancy">Open</a>` : ""}
                </div>
              </div>
            </div>
            ${tags ? `<div class="tags">${tags}</div>` : ""}
            ${job.description_preview ? `<p class="preview">${esc(job.description_preview)}${job.description_preview.length >= 420 ? "..." : ""}</p>` : ""}
            ${renderJobDetails(job, detailsId)}
          </article>
        `;
      }).join("");
    }

    async function loadFacets() {
      addLog("Facets", "Loading local database facets.");
      const response = await fetch("/api/facets");
      const facets = await response.json();
      setOptions(document.querySelector("#source"), facets.sources || []);
      setOptions(document.querySelector("#role"), mergeFacetItems([
        ...(facets.terms?.role_family_primary || []),
        ...(facets.terms?.role_family || [])
      ]));
      setOptions(document.querySelector("#seniority"), facets.terms?.seniority || []);
      setOptions(document.querySelector("#location"), facets.locations || []);
      setDatalist("#skill-list", mergeFacetItems([
        ...(facets.terms?.programming_language || []),
        ...(facets.terms?.framework_library || []),
        ...(facets.terms?.cloud_platform || []),
        ...(facets.terms?.database || []),
        ...(facets.terms?.tool || [])
      ]));
      setDatalist("#keyword-list", mergeFacetItems([
        ...(facets.terms?.programming_language || []),
        ...(facets.terms?.framework_library || []),
        ...(facets.terms?.cloud_platform || []),
        ...(facets.terms?.database || []),
        ...(facets.terms?.tool || []),
        ...(facets.terms?.methodology || [])
      ]));
      subtitleEl.textContent = `${facets.total || 0} local vacancies across ${(facets.databases || []).length} database(s).`;
      databaseSummaryEl.innerHTML = renderSummaryBlock("Sources", facets.sources || []);
      renderErrors(facets.database_errors);
      addLog("Facets", `Loaded ${facets.total || 0} vacancies across ${(facets.databases || []).length} database(s).`, facets.database_errors?.length ? "warning" : "success");
    }

    async function runSearch(page = currentPage) {
      addLog("Vacancy Search", `Searching local databases, page ${page}.`);
      resultsEl.innerHTML = '<div class="empty">Searching local databases...</div>';
      paginationEl.innerHTML = "";
      const response = await fetch(`/api/search?${buildParams(page).toString()}`);
      const payload = await response.json();
      if (!response.ok) {
        resultsEl.innerHTML = `<div class="error">${esc(payload.error || "Search failed")}</div>`;
        addLog("Vacancy Search", payload.error || "Search failed.", "error");
        return;
      }
      renderResults(payload);
      addLog("Vacancy Search", `Found ${payload.total ?? payload.count ?? 0} matching vacancies.`, payload.database_errors?.length ? "warning" : "success");
    }

    function renderKeywordCloud(container, keywords, emptyText) {
      if (!keywords || !keywords.length) {
        container.innerHTML = `<span class="tag">${esc(emptyText)}</span>`;
        return;
      }
      container.innerHTML = keywords.map((keyword) => `<span class="tag keyword">${esc(keyword)}</span>`).join("");
    }

    function resumeMatchLabel(score) {
      if (score >= 80) return "Very Good Match";
      if (score >= 60) return "Good Match";
      if (score >= 40) return "Partial Match";
      return "Needs Tailoring";
    }

    function setResumeScoreBreakdown(score) {
      const normalized = Math.max(0, Math.min(100, Number(score || 0)));
      const skills = normalized;
      const experience = Math.max(0, Math.min(100, normalized - 4));
      const keywords = Math.max(0, Math.min(100, normalized + 2));
      resumeSkillsScoreEl.textContent = `${skills}%`;
      resumeExperienceScoreEl.textContent = `${experience}%`;
      resumeKeywordsScoreEl.textContent = `${keywords}%`;
      resumeSkillsMeterEl.style.width = `${skills}%`;
      resumeExperienceMeterEl.style.width = `${experience}%`;
      resumeKeywordsMeterEl.style.width = `${keywords}%`;
    }

    function resetResumePreview() {
      resumeVacancyLoadStatusEl.textContent = "Waiting for vacancy";
      resumeVacancyLoadStatusEl.classList.add("is-muted");
      resumeVacancyPreviewEl.innerHTML = `
        <h3>No vacancy loaded yet</h3>
        <div class="resume-preview-tags">
          <span class="tag">Waiting</span>
        </div>
        <p>Paste a vacancy URL or fallback description, then run the matcher to preview the vacancy context used for the analysis.</p>
      `;
      setResumeScoreBreakdown(0);
      resumeScoreValueEl.style.setProperty("--score", 0);
    }

    function renderResumeVacancyPreview(vacancy, payload, requiredKeywords = []) {
      const fallbackText = String(payload.job_description || "").trim();
      const title = vacancy.title || payload.target_title || "Vacancy preview";
      const description = String(vacancy.description_text || fallbackText || "").trim();
      const preview = description
        ? `${description.slice(0, 700)}${description.length > 700 ? "..." : ""}`
        : "The matcher used the URL and available metadata, but no long description was available.";
      const tags = [
        vacancy.location,
        vacancy.company,
        vacancy.source,
        ...requiredKeywords.slice(0, 4),
      ].filter(Boolean);
      resumeVacancyPreviewEl.innerHTML = `
        <h3>${esc(title)}</h3>
        <div class="resume-preview-tags">
          ${tags.length ? tags.map((item) => `<span class="tag">${esc(item)}</span>`).join("") : '<span class="tag">Vacancy context</span>'}
        </div>
        <p>${esc(preview)}</p>
      `;
    }

    function renderResumeRecommendations(items) {
      if (!items || !items.length) {
        resumeRecommendationsEl.innerHTML = '<div class="empty">No recommendations generated.</div>';
        return;
      }
      resumeRecommendationsEl.innerHTML = items.map((item, index) => `
        <div class="resume-recommendation">
          <span class="resume-recommendation-icon">${index + 1}</span>
          <span><strong>${esc(item.split(":")[0] || "Recommendation")}</strong><span>${esc(item.includes(":") ? item.split(":").slice(1).join(":").trim() : item)}</span></span>
        </div>
      `).join("");
    }

    function setResumePdfDownload(pdf) {
      if (resumePdfObjectUrl) {
        URL.revokeObjectURL(resumePdfObjectUrl);
        resumePdfObjectUrl = "";
      }
      if (!pdf?.base64) {
        resumeDownloadPdfEl.hidden = true;
        resumeDownloadPdfEl.removeAttribute("href");
        return;
      }
      const binary = atob(pdf.base64);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      const blob = new Blob([bytes], { type: pdf.mime_type || "application/pdf" });
      resumePdfObjectUrl = URL.createObjectURL(blob);
      resumeDownloadPdfEl.href = resumePdfObjectUrl;
      resumeDownloadPdfEl.download = pdf.filename || "tailored-resume.pdf";
      resumeDownloadPdfEl.hidden = false;
    }

    function readFileAsBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.addEventListener("load", () => {
          const value = String(reader.result || "");
          resolve(value.includes(",") ? value.split(",", 2)[1] : value);
        });
        reader.addEventListener("error", () => reject(reader.error || new Error("Could not read PDF file.")));
        reader.readAsDataURL(file);
      });
    }

    async function runResumeMatch() {
      const formData = new FormData(resumeMatchFormEl);
      const payload = Object.fromEntries(formData.entries());
      delete payload.resume_pdf;
      resumeStatusEl.textContent = "Generating resume match...";
      resumeVacancyLoadStatusEl.textContent = "Loading vacancy...";
      resumeVacancyLoadStatusEl.classList.add("is-muted");
      resumeScoreCardEl.hidden = true;
      resumeRecommendationsEl.innerHTML = '<div class="empty">Generating resume match...</div>';
      renderKeywordCloud(resumeMatchedKeywordsEl, [], "Waiting");
      renderKeywordCloud(resumeMissingKeywordsEl, [], "Waiting");
      resumeResultEl.value = "";
      setResumePdfDownload(null);
      addLog("Resume matcher", "Generating resume match.");

      try {
        const file = resumePdfInputEl.files?.[0];
        if (file) {
          if (file.type && file.type !== "application/pdf") {
            throw new Error("Attach a PDF resume file.");
          }
          payload.resume_pdf_name = file.name;
          payload.resume_pdf_base64 = await readFileAsBase64(file);
        }
        const response = await fetch("/api/resume-match", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          resumeStatusEl.textContent = data.error || "Resume match failed.";
          resumeVacancyLoadStatusEl.textContent = "Vacancy load failed";
          resumeVacancyLoadStatusEl.classList.add("is-muted");
          resumeRecommendationsEl.innerHTML = `<div class="error">${esc(data.error || "Resume match failed.")}</div>`;
          addLog("Resume matcher", data.error || "Resume match failed.", "error");
          return;
        }
        const vacancy = data.vacancy || {};
        resumeStatusEl.textContent = data.vacancy_found
          ? "Vacancy loaded from local database."
          : data.vacancy_fetched
            ? "Vacancy page fetched from URL."
            : "Using pasted vacancy description because the URL was not found locally or could not be fetched.";
        resumeVacancyLoadStatusEl.textContent = data.vacancy_found || data.vacancy_fetched
          ? "Vacancy loaded successfully"
          : "Using pasted vacancy text";
        resumeVacancyLoadStatusEl.classList.toggle("is-muted", !(data.vacancy_found || data.vacancy_fetched));
        if (data.vacancy_fetch_error) {
          addLog("Resume matcher", data.vacancy_fetch_error, "warning");
        }
        renderResumeVacancyPreview(vacancy, payload, data.required_keywords || []);
        resumeScoreCardEl.hidden = false;
        const score = Number(data.score || 0);
        resumeScoreValueEl.textContent = `${score}%`;
        resumeScoreValueEl.style.setProperty("--score", score);
        setResumeScoreBreakdown(score);
        resumeVacancyTitleEl.textContent = resumeMatchLabel(score);
        resumeVacancyMetaEl.textContent = [
          vacancy.company,
          vacancy.location,
          vacancy.source,
        ].filter(Boolean).join(" · ") || (vacancy.title || payload.target_title || "Local keyword alignment");
        renderKeywordCloud(resumeMatchedKeywordsEl, data.matched_keywords || [], "No matched keywords yet");
        renderKeywordCloud(resumeMissingKeywordsEl, data.missing_keywords || [], "No missing keywords found");
        renderResumeRecommendations(data.recommendations || []);
        resumeResultEl.value = data.tailored_resume || "";
        setResumePdfDownload(data.tailored_resume_pdf);
        renderErrors(data.database_errors);
        addLog(
          "Resume matcher",
          `Generated resume match with ${Number(data.score || 0)}% keyword alignment${data.resume_pdf_text_extracted ? " from attached PDF" : ""}.`,
          data.vacancy_found ? "success" : "warning",
        );
      } catch (error) {
        resumeStatusEl.textContent = error.message || String(error);
        resumeVacancyLoadStatusEl.textContent = "Vacancy load failed";
        resumeVacancyLoadStatusEl.classList.add("is-muted");
        resumeRecommendationsEl.innerHTML = `<div class="error">${esc(error.message || String(error))}</div>`;
        addLog("Resume matcher", error.message || String(error), "error");
      }
    }

    async function copyResumeDraft() {
      const text = resumeResultEl.value.trim();
      if (!text) {
        addLog("Resume matcher", "No generated draft to copy.", "warning");
        return;
      }
      try {
        await navigator.clipboard.writeText(text);
        addLog("Resume matcher", "Copied tailored resume draft.", "success");
      } catch {
        resumeResultEl.focus();
        resumeResultEl.select();
        document.execCommand("copy");
        addLog("Resume matcher", "Copied tailored resume draft.", "success");
      }
    }

    menuButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const view = button.dataset.viewTarget;
        if (!view || view === currentView) return;
        setView(view);
      });
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      setView("vacancies");
      currentPage = 1;
      runSearch(1);
    });
    resetBtn.addEventListener("click", () => {
      form.reset();
      syncSalaryInputsFromRange();
      currentPage = 1;
      addLog("Vacancy Search", "Cleared search filters.");
      runSearch(1);
    });
    resumeMatchFormEl.addEventListener("submit", (event) => {
      event.preventDefault();
      runResumeMatch();
    });
    resumeResetEl.addEventListener("click", () => {
      resumeMatchFormEl.reset();
      resumeStatusEl.textContent = "No resume match generated yet.";
      resumeScoreCardEl.hidden = true;
      renderKeywordCloud(resumeMatchedKeywordsEl, [], "Waiting");
      renderKeywordCloud(resumeMissingKeywordsEl, [], "Waiting");
      resumeRecommendationsEl.innerHTML = '<div class="empty">Run the matcher to see recommendations.</div>';
      resumeResultEl.value = "";
      resumeFileNameEl.textContent = "No PDF selected";
      resetResumePreview();
      setResumePdfDownload(null);
      addLog("Resume matcher", "Cleared resume matcher inputs.");
    });
    resumeCopyEl.addEventListener("click", copyResumeDraft);
    resumePdfInputEl.addEventListener("change", () => {
      const file = resumePdfInputEl.files?.[0];
      resumeFileNameEl.textContent = file ? file.name : "No PDF selected";
    });
    resumeClearFileEl.addEventListener("click", () => {
      resumePdfInputEl.value = "";
      resumeFileNameEl.textContent = "No PDF selected";
      addLog("Resume matcher", "Removed attached PDF.");
    });
    paginationEl.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-page]");
      if (!button || button.disabled) return;
      const page = Number(button.dataset.page);
      if (!Number.isFinite(page)) return;
      runSearch(page);
    });
    resultsEl.addEventListener("click", (event) => {
      const jsonButton = event.target.closest("button[data-json-toggle]");
      if (jsonButton) {
        const panel = jsonButton.closest(".job-details-panel");
        const sections = panel ? Array.from(panel.querySelectorAll(".json-section")) : [];
        const isExpanded = jsonButton.getAttribute("aria-expanded") === "true";
        jsonButton.setAttribute("aria-expanded", String(!isExpanded));
        jsonButton.textContent = isExpanded ? "Show JSON" : "Hide JSON";
        sections.forEach((section) => {
          section.hidden = isExpanded;
        });
        return;
      }

      const button = event.target.closest("button[data-details-target]");
      if (button) {
        const panel = document.getElementById(button.dataset.detailsTarget);
        if (!panel) return;
        const isExpanded = button.getAttribute("aria-expanded") === "true";
        button.setAttribute("aria-expanded", String(!isExpanded));
        button.textContent = isExpanded ? "Details" : "Hide details";
        panel.hidden = isExpanded;
        const preview = button.closest(".job")?.querySelector(".preview");
        if (preview) {
          preview.hidden = !isExpanded;
        }
      }
    });
    salaryMinRange.addEventListener("input", () => syncSalaryInputsFromRange("min"));
    salaryMaxRange.addEventListener("input", () => syncSalaryInputsFromRange("max"));
    salaryMinInput.addEventListener("input", syncSalaryRangeFromInputs);
    salaryMaxInput.addEventListener("input", syncSalaryRangeFromInputs);

    document.querySelector("#parser-workspace .btn.primary")?.addEventListener("click", () => {
      startParserRun();
    });
    document.querySelector("#parser-workspace .btn.secondary")?.addEventListener("click", () => {
      const payload = collectParserPayload();
      const args = [
        payload.mode ? `--mode ${payload.mode}` : "",
        payload.canton ? `--canton ${payload.canton}` : "",
        payload.term ? `--term ${payload.term}` : "",
        payload.location ? `--location ${payload.location}` : "",
        payload.max_pages ? `--max-pages ${payload.max_pages}` : "",
        payload.detail_limit ? `--detail-limit ${payload.detail_limit}` : "",
      ].filter(Boolean).join(" ");
      const sourceText = payload.sources.length ? payload.sources.join(", ") : "no sources selected";
      addLog("Vacancy Collection", `Preview for ${sourceText}: python -m swiss_jobs.cli.parse --source <source> ${args}`.trim(), "info");
      setLogDrawer(true);
    });
    document.querySelector("#ai-analyse-workspace .btn.primary")?.addEventListener("click", () => {
      startAiAnalysisRun();
    });
    document.querySelector("#ai-analyse-workspace .btn.secondary")?.addEventListener("click", () => {
      const payload = collectAiAnalysisPayload();
      const args = [
        `--model ${payload.model}`,
        payload.first_seen_from ? `--first-seen-from ${payload.first_seen_from}` : "",
        payload.first_seen_to ? `--first-seen-to ${payload.first_seen_to}` : "",
        payload.scope === "all selected vacancies" ? "--include-analyzed" : "",
        payload.scope === "all selected vacancies" && !payload.limit ? "--all" : "",
        payload.limit ? `--limit ${payload.limit}` : "",
      ].filter(Boolean).join(" ");
      const sourceText = payload.sources.length ? payload.sources.join(", ") : "no sources selected";
      addLog("AI Analyse", `Preview for ${sourceText}: python -m swiss_jobs.cli.analyze_vacancies_llm --source <source> ${args}`.trim(), "info");
      setLogDrawer(true);
    });
    document.querySelector("#public-stats-workspace .btn.primary")?.addEventListener("click", () => {
      startPublicStatsRun();
    });
    document.querySelector("#public-stats-workspace .btn.secondary")?.addEventListener("click", () => {
      const payload = collectPublicStatsPayload();
      const sourceText = payload.sources.length ? payload.sources.join(", ") : "no sources selected";
      addLog(
        "Public Stats",
        `Preview for ${sourceText}: export analytics${payload.salary_group_minimum ? ` with salary groups >= ${payload.salary_group_minimum}` : ""} -> build ${payload.output_dir}/data + ${payload.output_dir}/csv${payload.snapshot_date ? ` for ${payload.snapshot_date}` : ""} -> sync ${payload.site_dir}.`,
        "info",
      );
      setLogDrawer(true);
    });
    logToggleEl.addEventListener("click", () => {
      setLogDrawer(logToggleEl.getAttribute("aria-expanded") !== "true");
    });
    logCloseEl.addEventListener("click", () => setLogDrawer(false));
    logClearEl.addEventListener("click", () => {
      logs.length = 0;
      renderLogs();
      addLog("Logs", "Log history cleared.");
    });

    syncSalaryTrack();
    renderKeywordCloud(resumeMatchedKeywordsEl, [], "Waiting");
    renderKeywordCloud(resumeMissingKeywordsEl, [], "Waiting");
    renderLogs();
    addLog("Application", "Local vacancy interface initialized.");
    loadFacets().then(runSearch).catch((error) => {
      resultsEl.innerHTML = `<div class="error">${esc(error.message || error)}</div>`;
      addLog("Application", error.message || String(error), "error");
    });
  </script>
</body>
</html>
"""


def serve(config: LocalSearchConfig, *, open_browser: bool = False) -> None:
    handler_class = type(
        "ConfiguredLocalSearchHandler",
        (LocalSearchHandler,),
        {"config": config},
    )
    server = ThreadingHTTPServer((config.host, config.port), handler_class)
    urls = _display_urls(config.host, server.server_port)
    print(f"Local vacancy search is running at {urls[0]}")
    if len(urls) > 1:
        print("Network access URLs:")
        for url in urls[1:]:
            print(f"  - {url}")
        print("Use these URLs only on a trusted local network; this app exposes local data and run controls.")
    print("Loaded databases:")
    for path in config.database_paths:
        print(f"  - {path}")
    if open_browser:
        webbrowser.open(_browser_open_url(config.host, server.server_port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local vacancy search.")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        database_paths = tuple(_resolve_database_paths(args.database_path))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not database_paths:
        defaults = ", ".join(str(path) for path in DEFAULT_RUNTIME_DATABASES)
        print(f"error: no local databases found. Checked: {defaults}", file=sys.stderr)
        return 2

    host = args.host or ("0.0.0.0" if args.share_lan else "127.0.0.1")
    serve(
        LocalSearchConfig(database_paths=database_paths, host=host, port=args.port),
        open_browser=args.open,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import base64
import html
import ipaddress
import io
import json
import os
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

from swiss_jobs.core.llm_analysis import RequestsOpenAIResponsesTransport
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


def _static_response(
    handler: BaseHTTPRequestHandler,
    asset_path: Path,
    content_type: str,
    *,
    include_body: bool = True,
) -> None:
    try:
        data = asset_path.read_bytes()
        status = HTTPStatus.OK
    except OSError:
        data = b"Not found"
        status = HTTPStatus.NOT_FOUND
        content_type = "text/plain; charset=utf-8"

    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", STATIC_CACHE_CONTROL)
    handler.end_headers()
    if include_body:
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


def _strip_dotenv_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value.split(" #", 1)[0].strip()


def _project_dotenv_value(key: str) -> str:
    dotenv_path = PROJECT_ROOT / ".env"
    if not dotenv_path.is_file():
        return ""
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        raw_key, raw_value = line.split("=", 1)
        if raw_key.strip() == key:
            return _strip_dotenv_value(raw_value.strip())
    return ""


def _openai_api_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or _project_dotenv_value("OPENAI_API_KEY")).strip()


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


def _dotenv_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _replace_dotenv_values(path: Path, updates: dict[str, str | None]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    seen: set[str] = set()
    next_lines: list[str] = []
    for raw_line in existing_lines:
        line = raw_line.strip()
        probe = line[len("export ") :].lstrip() if line.startswith("export ") else line
        if not line or line.startswith("#") or "=" not in probe:
            next_lines.append(raw_line)
            continue
        key = probe.split("=", 1)[0].strip()
        if key not in updates:
            next_lines.append(raw_line)
            continue
        seen.add(key)
        value = updates[key]
        if value is not None:
            next_lines.append(f"{key}={_dotenv_quote(value)}")
    for key, value in updates.items():
        if key not in seen and value is not None:
            next_lines.append(f"{key}={_dotenv_quote(value)}")
    content = "\n".join(next_lines).rstrip()
    path.write_text((content + "\n") if content else "", encoding="utf-8")


def update_openai_settings(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = _clean_text(payload.get("api_key"))
    if api_key:
        _replace_dotenv_values(PROJECT_ROOT / ".env", {"OPENAI_API_KEY": api_key})
    return {"api_key_configured": bool(api_key)}


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


def _clamp_score(value: Any) -> int:
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def _normalize_short_text_list(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text[:220])
        if len(result) >= limit:
            break
    return result


def _normalize_resume_gap_items(value: Any, *, limit: int = 8) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        requirement = " ".join(str(item.get("requirement") or "").strip().split())
        resume_gap = " ".join(str(item.get("resume_gap") or "").strip().split())
        recommended_change = " ".join(str(item.get("recommended_change") or "").strip().split())
        if not requirement and not resume_gap and not recommended_change:
            continue
        result.append(
            {
                "requirement": requirement[:160],
                "resume_gap": resume_gap[:260],
                "recommended_change": recommended_change[:300],
            }
        )
        if len(result) >= limit:
            break
    return result


def _resume_match_json_schema() -> dict[str, Any]:
    score_schema = {"type": "integer", "minimum": 0, "maximum": 100}
    text_array_schema = {
        "type": "array",
        "items": {"type": "string", "maxLength": 220},
        "maxItems": 12,
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "overall_score": score_schema,
            "skills_score": score_schema,
            "experience_score": score_schema,
            "keywords_score": score_schema,
            "matched_keywords": text_array_schema,
            "missing_keywords": text_array_schema,
            "key_strengths": text_array_schema,
            "critical_gaps": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "requirement": {"type": "string", "maxLength": 160},
                        "resume_gap": {"type": "string", "maxLength": 260},
                        "recommended_change": {"type": "string", "maxLength": 300},
                    },
                    "required": ["requirement", "resume_gap", "recommended_change"],
                },
            },
            "recommendations": {
                "type": "array",
                "items": {"type": "string", "maxLength": 320},
                "maxItems": 6,
            },
            "tailored_resume": {"type": "string", "maxLength": 12000},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "confidence_reason": {"type": "string", "maxLength": 320},
        },
        "required": [
            "overall_score",
            "skills_score",
            "experience_score",
            "keywords_score",
            "matched_keywords",
            "missing_keywords",
            "key_strengths",
            "critical_gaps",
            "recommendations",
            "tailored_resume",
            "confidence",
            "confidence_reason",
        ],
    }


def _resume_match_system_prompt() -> str:
    return (
        "You are an expert Swiss IT recruiter and ATS resume reviewer. "
        "Evaluate how well the candidate resume matches the vacancy. "
        "Base every score on explicit evidence in the vacancy and resume. "
        "Do not reward unsupported claims, generic filler, or keyword stuffing. "
        "Score strictly: 90-100 means near-perfect direct match, 70-89 strong match with small gaps, "
        "50-69 partial match, 30-49 weak match, below 30 poor match. "
        "Skills score should measure required technologies, tools, domains, languages, and methods. "
        "Experience score should measure seniority, role scope, responsibilities, impact, leadership, "
        "industry/domain fit, and evidence quality. "
        "Keywords score should measure ATS wording coverage for important vacancy terms, excluding generic words. "
        "Return concise, actionable recommendations that tell the candidate exactly what to change. "
        "Tailor the resume draft truthfully; never invent employers, degrees, years, metrics, or projects. "
        "If information is missing, use bracketed placeholders such as [add metric] instead of inventing facts."
    )


def _resume_match_user_payload(
    *,
    vacancy_title: str,
    company: str,
    vacancy_source: dict[str, Any],
    vacancy_text: str,
    resume_text: str,
    analytics: dict[str, Any],
) -> str:
    payload = {
        "vacancy": {
            "title": vacancy_title,
            "company": company,
            "source": vacancy_source.get("source") or "",
            "location": vacancy_source.get("location") or "",
            "url": vacancy_source.get("url") or "",
            "description_text": vacancy_text[:12000],
            "analytics_hints": analytics,
        },
        "candidate_resume": resume_text[:18000],
        "task": {
            "goal": "score match quality and produce a truthful vacancy-tailored resume draft",
            "audience": "Swiss IT recruiter and ATS screening",
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _extract_openai_response_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    output = response.get("output")
    if not isinstance(output, list):
        raise ValueError("OpenAI response does not contain output text.")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        for content_item in item.get("content", []) or []:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    if not parts:
        raise ValueError("OpenAI response does not contain message text.")
    return "\n".join(parts)


def _normalize_llm_resume_match(payload: dict[str, Any], *, resume_text: str) -> dict[str, Any]:
    recommendations = _normalize_short_text_list(payload.get("recommendations"), limit=6)
    gaps = _normalize_resume_gap_items(payload.get("critical_gaps"))
    if not recommendations:
        recommendations = [
            item["recommended_change"]
            for item in gaps
            if item.get("recommended_change")
        ][:6]
    tailored_resume = str(payload.get("tailored_resume") or "").strip()
    if not tailored_resume:
        tailored_resume = resume_text
    return {
        "score": _clamp_score(payload.get("overall_score")),
        "score_breakdown": {
            "skills": _clamp_score(payload.get("skills_score")),
            "experience": _clamp_score(payload.get("experience_score")),
            "keywords": _clamp_score(payload.get("keywords_score")),
        },
        "matched_keywords": _normalize_short_text_list(payload.get("matched_keywords"), limit=12),
        "missing_keywords": _normalize_short_text_list(payload.get("missing_keywords"), limit=12),
        "key_strengths": _normalize_short_text_list(payload.get("key_strengths"), limit=12),
        "critical_gaps": gaps,
        "recommendations": recommendations,
        "tailored_resume": tailored_resume,
        "confidence": str(payload.get("confidence") or "").strip(),
        "confidence_reason": str(payload.get("confidence_reason") or "").strip(),
    }


def build_llm_resume_match(
    *,
    model: str,
    vacancy_title: str,
    company: str,
    vacancy_source: dict[str, Any],
    vacancy_text: str,
    analytics: dict[str, Any],
    resume_text: str,
    api_key: str | None = None,
    transport: Any | None = None,
) -> dict[str, Any]:
    clean_model = _clean_text(model) or "gpt-5.5"
    clean_api_key = (api_key or _openai_api_key()).strip()
    if not clean_api_key:
        raise ValueError("OPENAI_API_KEY is not set. Save it in Settings before running resume match.")
    client = transport or RequestsOpenAIResponsesTransport()
    response = client.create_response(
        {
            "model": clean_model,
            "store": False,
            "reasoning": {"effort": "medium"},
            "max_output_tokens": 2400,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "resume_match_analysis",
                    "strict": True,
                    "schema": _resume_match_json_schema(),
                }
            },
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": _resume_match_system_prompt()}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _resume_match_user_payload(
                                vacancy_title=vacancy_title,
                                company=company,
                                vacancy_source=vacancy_source,
                                vacancy_text=vacancy_text,
                                analytics=analytics,
                                resume_text=resume_text,
                            ),
                        }
                    ],
                },
            ],
        },
        api_key=clean_api_key,
        timeout_seconds=90.0,
    )
    text = _extract_openai_response_text(response)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI returned invalid resume match JSON: {text[:500]!r}") from exc
    if not isinstance(payload, dict):
        raise ValueError("OpenAI returned non-object resume match JSON.")
    result = _normalize_llm_resume_match(payload, resume_text=resume_text)
    result["model"] = clean_model
    return result


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


def _find_resume_vacancy_by_id(
    database_paths: Iterable[Path],
    vacancy_database: str,
    vacancy_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    clean_id = _clean_text(vacancy_id)
    clean_database = _clean_text(vacancy_database)
    if not clean_id:
        return None, []

    query = """
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
        WHERE v.vacancy_id = ?
        LIMIT 1
    """
    database_errors: list[dict[str, str]] = []

    for database_path in database_paths:
        if clean_database and str(database_path) != clean_database:
            continue
        try:
            connection = _connect_readonly(database_path)
            try:
                row = connection.execute(query, [clean_id]).fetchone()
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


def build_resume_match(
    database_paths: Iterable[Path],
    payload: dict[str, Any],
    *,
    openai_transport: Any | None = None,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    vacancy_url = _clean_text(payload.get("vacancy_url"))
    vacancy_id = _clean_text(payload.get("vacancy_id"))
    vacancy_database = _clean_text(payload.get("vacancy_database"))
    resume_pdf_text = extract_resume_pdf_text(payload)
    resume_text = resume_pdf_text or _clean_text(payload.get("resume_text"))
    pasted_description = _clean_text(payload.get("job_description"))
    if vacancy_id:
        vacancy, database_errors = _find_resume_vacancy_by_id(database_paths, vacancy_database, vacancy_id)
        if not vacancy and vacancy_url:
            vacancy, url_database_errors = _find_resume_vacancy(database_paths, vacancy_url)
            database_errors.extend(url_database_errors)
    else:
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
    llm_match = build_llm_resume_match(
        model=_clean_text(payload.get("model")) or "gpt-5.5",
        vacancy_title=vacancy_title,
        company=company,
        vacancy_source=vacancy_source,
        vacancy_text=vacancy_text,
        analytics=analytics,
        resume_text=resume_text,
        api_key=openai_api_key,
        transport=openai_transport,
    )
    tailored_resume = llm_match["tailored_resume"]
    target_line = vacancy_title or "Target role"
    pdf_bytes = build_resume_pdf_bytes(tailored_resume, title=target_line)

    return {
        "vacancy_found": bool(vacancy),
        "vacancy_fetched": bool(fetched_vacancy),
        "vacancy_fetch_error": vacancy_fetch_error,
        "vacancy": vacancy_source or None,
        "score": llm_match["score"],
        "score_breakdown": llm_match["score_breakdown"],
        "required_keywords": [*llm_match["matched_keywords"], *llm_match["missing_keywords"]],
        "matched_keywords": llm_match["matched_keywords"],
        "missing_keywords": llm_match["missing_keywords"],
        "key_strengths": llm_match["key_strengths"],
        "critical_gaps": llm_match["critical_gaps"],
        "recommendations": llm_match["recommendations"],
        "tailored_resume": tailored_resume,
        "tailored_resume_pdf": {
            "filename": _resume_pdf_filename(target_line),
            "mime_type": "application/pdf",
            "base64": base64.b64encode(pdf_bytes).decode("ascii"),
        },
        "resume_pdf_text_extracted": bool(resume_pdf_text),
        "match_model": llm_match["model"],
        "match_confidence": llm_match["confidence"],
        "match_confidence_reason": llm_match["confidence_reason"],
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
    index_html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    return index_html.replace("__DATABASE_LIST__", database_list)


def _static_asset(path: str) -> tuple[Path, str] | None:
    return STATIC_ASSETS.get(path)


class LocalSearchHandler(BaseHTTPRequestHandler):
    config: LocalSearchConfig

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        static_asset = _static_asset(parsed.path)
        if static_asset is not None:
            _static_response(self, *static_asset, include_body=False)
            return
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
            static_asset = _static_asset(parsed.path)
            if static_asset is not None:
                _static_response(self, *static_asset)
                return
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
            if parsed.path == "/api/settings/openai":
                _json_response(self, update_openai_settings(_json_body(self)))
                return
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        _text_response(self, "Not found", status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[local-search] {self.address_string()} {format % args}", file=sys.stderr)


INDEX_HTML_PATH = Path(__file__).with_name("local_search_web.html")
ASSETS_DIR = Path(__file__).with_name("assets")
STATIC_CACHE_CONTROL = "no-cache"
STATIC_ASSETS = {
    "/assets/styles.css": (ASSETS_DIR / "styles.css", "text/css; charset=utf-8"),
    "/assets/app.js": (ASSETS_DIR / "app.js", "application/javascript; charset=utf-8"),
}


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

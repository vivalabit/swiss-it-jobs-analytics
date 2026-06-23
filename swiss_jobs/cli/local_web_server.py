from __future__ import annotations

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
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from swiss_jobs.core.locations import location_search_terms, normalize_location_display
from swiss_jobs.registry import list_supported_sources

from .resume_matcher import build_resume_match, build_tailored_resume_cv, build_tailored_resume_pdf
from .search_vacancies import _split_csv_values
from .static import (
    _head_response,
    _html_response,
    _json_response,
    _static_asset,
    _static_response,
    _text_response,
    render_index,
)

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

@dataclass(frozen=True)
class LocalSearchConfig:
    database_paths: tuple[Path, ...]
    host: str
    port: int

def _connect_readonly(database_path: Path) -> sqlite3.Connection:
    uri = database_path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection

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
            if parsed.path == "/api/resume-pdf":
                _json_response(self, build_tailored_resume_pdf(_json_body(self)))
                return
            if parsed.path == "/api/resume-cv":
                _json_response(self, build_tailored_resume_cv(_json_body(self)))
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

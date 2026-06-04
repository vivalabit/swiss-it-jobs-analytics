from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from .search_vacancies import DEFAULT_RUNTIME_DATABASES, _resolve_database_paths, _split_csv_values

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
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port. Defaults to 8765.")
    parser.add_argument("--open", action="store_true", help="Open the page in the default browser.")
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
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError(f"{name} must use YYYY-MM-DD format")
    return raw


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
        clauses.append("lower(v.place) LIKE ?")
        values.append(f"%{location}%")

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

    seniority = (params.get("seniority") or [""])[0].strip().lower()
    if seniority:
        clauses.append(
            """
            EXISTS (
                SELECT 1 FROM vacancy_terms vt
                WHERE vt.vacancy_id = v.vacancy_id
                  AND vt.term_type = 'seniority'
                  AND lower(vt.term_value) = ?
            )
            """
        )
        values.append(seniority)

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
    limit = _request_int(params, "limit", 100) or 100
    limit = max(1, min(limit, 500))
    where, values, words = _build_where(params)
    rows: list[dict[str, Any]] = []
    database_errors: list[dict[str, str]] = []

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
            v.analytics_json,
            v.first_seen_at,
            v.last_seen_at,
            v.description_text
        FROM vacancies v
        {where}
        ORDER BY
            v.last_seen_at DESC,
            COALESCE(v.salary_max, v.salary_min) DESC,
            v.vacancy_id ASC
        LIMIT ?
    """

    for database_path in database_paths:
        try:
            connection = _connect_readonly(database_path)
            try:
                fetched = connection.execute(query, [*values, limit]).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            database_errors.append({"database": str(database_path), "error": str(exc)})
            continue

        for row in fetched:
            analytics = _load_json_object(row["analytics_json"])
            matched_keywords = _load_json_list(row["keywords_matched_json"])
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
                    "location": row["place"] or "",
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
                    "seniority": ", ".join(_listify(analytics.get("seniority_labels"))),
                    "remote_mode": analytics.get("remote_mode") or "",
                    "matched_keywords": matched_keywords[:10],
                    "skills": sorted({str(skill) for skill in skills if str(skill).strip()})[:10],
                    "score": _row_score(row, words),
                    "description_preview": str(row["description_text"] or "").strip()[:420],
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
    return {
        "count": len(rows[:limit]),
        "results": rows[:limit],
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
                    place = str(row["place"] or "")
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
        if parsed.path in {"/api/search", "/api/facets", "/health"}:
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
            if parsed.path == "/health":
                _json_response(self, {"ok": True})
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
      --ink: #17202a;
      --muted: #647180;
      --line: #d8dee5;
      --field: #ffffff;
      --surface: #f6f7f4;
      --panel: #ffffff;
      --accent: #b4232a;
      --accent-dark: #8e1d23;
      --green: #1f7a5f;
      --blue: #2364aa;
      --amber: #a45f12;
      --shadow: 0 12px 32px rgba(23, 32, 42, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--surface);
      color: var(--ink);
      letter-spacing: 0;
    }
    button, input, select, textarea { font: inherit; }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
    }
    aside {
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      background: #fdfdfb;
      border-right: 1px solid var(--line);
      padding: 22px;
    }
    main {
      min-width: 0;
      padding: 22px 26px 32px;
    }
    h1 {
      margin: 0 0 4px;
      font-size: 22px;
      line-height: 1.2;
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
      color: #344150;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 6px;
      text-transform: uppercase;
    }
    input, select, textarea {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--field);
      color: var(--ink);
      padding: 9px 10px;
      outline: none;
    }
    textarea {
      min-height: 68px;
      resize: vertical;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--blue);
      box-shadow: 0 0 0 3px rgba(35, 100, 170, 0.16);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .actions {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      margin-top: 18px;
    }
    .btn {
      min-height: 42px;
      border: 1px solid transparent;
      border-radius: 7px;
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
      background: var(--accent);
      color: white;
    }
    .btn.primary:hover { background: var(--accent-dark); }
    .btn.secondary {
      background: #ffffff;
      border-color: var(--line);
      color: var(--ink);
    }
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
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
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #ffffff;
      padding: 3px 10px;
    }
    .database-summary {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 16px;
    }
    .summary-block {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 12px;
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
    .job {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: var(--shadow);
    }
    .job-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: start;
    }
    .job h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.28;
    }
    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 12px;
      color: var(--muted);
      font-size: 13px;
      margin-top: 7px;
    }
    .salary {
      color: var(--green);
      font-weight: 800;
      white-space: nowrap;
    }
    .tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 12px;
    }
    .tag {
      border-radius: 999px;
      background: #eef3f0;
      color: #1f473c;
      padding: 4px 9px;
      font-size: 12px;
      line-height: 1.2;
    }
    .tag.role { background: #eef3fb; color: #1e4c82; }
    .tag.warn { background: #fff2df; color: #7a4008; }
    .tag.keyword { background: #f1eef8; color: #4f3778; }
    .preview {
      color: #4b5968;
      font-size: 13px;
      line-height: 1.5;
      margin: 12px 0 0;
    }
    .open-link {
      min-height: 36px;
      border-radius: 7px;
      border: 1px solid var(--line);
      padding: 0 11px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--blue);
      text-decoration: none;
      font-weight: 800;
      white-space: nowrap;
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
    @media (max-width: 860px) {
      .app { grid-template-columns: 1fr; }
      aside {
        position: static;
        height: auto;
      }
      main { padding: 18px; }
      .job-head { grid-template-columns: 1fr; }
      .salary { white-space: normal; }
      .database-summary { grid-template-columns: 1fr; }
    }
    @media (max-width: 520px) {
      aside { padding: 18px; }
      .row, .actions { grid-template-columns: 1fr; }
      .toolbar { align-items: flex-start; flex-direction: column; }
      .btn { width: 100%; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <h1>Local Vacancy Search</h1>
      <p class="sub">Searches only the SQLite databases loaded from your local runtime folder.</p>
      <form id="search-form">
        <div class="field">
          <label for="q">Search</label>
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
            <input id="location" name="location" list="location-list" placeholder="Zurich">
            <datalist id="location-list"></datalist>
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
            <input id="date_from" name="date_from" type="date">
          </div>
          <div class="field">
            <label for="date_to">Date to</label>
            <input id="date_to" name="date_to" type="date">
          </div>
        </div>
        <div class="row">
          <div class="field">
            <label for="salary_min">Salary min <span>optional</span></label>
            <input id="salary_min" name="salary_min" type="number" inputmode="numeric" placeholder="110000">
          </div>
          <div class="field">
            <label for="salary_max">Salary max <span>optional</span></label>
            <input id="salary_max" name="salary_max" type="number" inputmode="numeric" placeholder="160000">
          </div>
        </div>
        <div class="row">
          <div class="field">
            <label for="limit">Limit</label>
            <select id="limit" name="limit">
              <option>50</option>
              <option selected>100</option>
              <option>200</option>
              <option>500</option>
            </select>
          </div>
          <div class="field">
            <label for="has_salary">Salary</label>
            <select id="has_salary" name="has_salary">
              <option value="">Any</option>
              <option value="1">Only with salary</option>
            </select>
          </div>
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
      <div class="toolbar">
        <div>
          <h1>Vacancies</h1>
          <p class="sub" id="subtitle">Loading local database facets...</p>
        </div>
        <div class="stats" id="stats"></div>
      </div>
      <div id="errors"></div>
      <section class="database-summary" id="database-summary" aria-label="Local database statistics"></section>
      <section class="results" id="results"></section>
    </main>
  </div>
  <script>
    const form = document.querySelector("#search-form");
    const resultsEl = document.querySelector("#results");
    const statsEl = document.querySelector("#stats");
    const errorsEl = document.querySelector("#errors");
    const databaseSummaryEl = document.querySelector("#database-summary");
    const subtitleEl = document.querySelector("#subtitle");
    const resetBtn = document.querySelector("#reset");

    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));

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

    function buildParams() {
      const data = new FormData(form);
      const params = new URLSearchParams();
      for (const [key, value] of data.entries()) {
        const clean = String(value).trim();
        if (clean) params.set(key, clean);
      }
      return params;
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

    function renderResults(payload) {
      renderErrors(payload.database_errors);
      statsEl.innerHTML = `
        <span class="pill">${esc(payload.count)} shown</span>
        <span class="pill">${new Date().toLocaleTimeString()}</span>
      `;
      if (!payload.results.length) {
        resultsEl.innerHTML = '<div class="empty">No vacancies match these filters.</div>';
        return;
      }
      resultsEl.innerHTML = payload.results.map((job) => {
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
              <div>
                <h2>${esc(job.title || "Untitled vacancy")}</h2>
                <div class="meta">
                  <span>${esc(job.company || "-")}</span>
                  <span>${esc(job.location || "-")}</span>
                  <span>${esc(job.source || "-")}</span>
                  <span>${esc(job.publication_date || job.last_seen_at || "-")}</span>
                </div>
              </div>
              <div>
                <div class="salary">${esc(job.salary || "")}</div>
                ${job.url ? `<a class="open-link" href="${esc(job.url)}" target="_blank" rel="noreferrer" title="Open original vacancy">Open</a>` : ""}
              </div>
            </div>
            ${tags ? `<div class="tags">${tags}</div>` : ""}
            ${job.description_preview ? `<p class="preview">${esc(job.description_preview)}${job.description_preview.length >= 420 ? "..." : ""}</p>` : ""}
          </article>
        `;
      }).join("");
    }

    async function loadFacets() {
      const response = await fetch("/api/facets");
      const facets = await response.json();
      setOptions(document.querySelector("#source"), facets.sources || []);
      setOptions(document.querySelector("#role"), mergeFacetItems([
        ...(facets.terms?.role_family_primary || []),
        ...(facets.terms?.role_family || [])
      ]));
      setOptions(document.querySelector("#seniority"), facets.terms?.seniority || []);
      setDatalist("#location-list", facets.locations || []);
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
      databaseSummaryEl.innerHTML = [
        renderSummaryBlock("SQLite databases", facets.database_stats || []),
        renderSummaryBlock("Sources", facets.sources || [])
      ].join("");
      renderErrors(facets.database_errors);
    }

    async function runSearch() {
      resultsEl.innerHTML = '<div class="empty">Searching local databases...</div>';
      const response = await fetch(`/api/search?${buildParams().toString()}`);
      const payload = await response.json();
      if (!response.ok) {
        resultsEl.innerHTML = `<div class="error">${esc(payload.error || "Search failed")}</div>`;
        return;
      }
      renderResults(payload);
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      runSearch();
    });
    resetBtn.addEventListener("click", () => {
      form.reset();
      runSearch();
    });

    loadFacets().then(runSearch).catch((error) => {
      resultsEl.innerHTML = `<div class="error">${esc(error.message || error)}</div>`;
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
    url = f"http://{config.host}:{server.server_port}/"
    print(f"Local vacancy search is running at {url}")
    print("Loaded databases:")
    for path in config.database_paths:
        print(f"  - {path}")
    if open_browser:
        webbrowser.open(url)
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

    serve(
        LocalSearchConfig(database_paths=database_paths, host=args.host, port=args.port),
        open_browser=args.open,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

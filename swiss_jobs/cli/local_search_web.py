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

from swiss_jobs.core.locations import location_search_terms, normalize_location_display

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

SEARCH_DEFAULT_PAGE_SIZE = 10
SEARCH_MAX_PAGE_SIZE = 100


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
      gap: 36px;
      align-items: start;
    }
    aside {
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
      aside {
        position: static;
        max-height: none;
      }
      main { padding: 18px; }
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
      aside { padding: 18px; }
      .row, .actions { grid-template-columns: 1fr; }
      .toolbar { align-items: flex-start; flex-direction: column; }
      .toolbar-actions { width: 100%; justify-content: space-between; }
      .database-summary {
        left: 0;
        right: auto;
        width: calc(100vw - 36px);
      }
      .btn { width: 100%; }
      main { padding: 0; }
      .job { padding: 18px; }
      .job-head { grid-template-columns: 1fr; }
      .company-mark, .tags, .preview, .job-details-panel { margin-left: 0; }
      .company-mark { border-radius: 8px; }
      .job-side, .job-actions { width: 100%; justify-items: stretch; }
      .job-actions > * { flex: 1 1 130px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
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
            <input id="date_from" name="date_from" type="date">
          </div>
          <div class="field">
            <label for="date_to">Date to</label>
            <input id="date_to" name="date_to" type="date">
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
      <div class="toolbar">
        <div>
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
    </main>
  </div>
  <script>
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
    let currentPage = 1;

    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
    const formatChf = (value) => `${Number(value).toLocaleString("en-US")} CHF`;

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

    function buildParams(page = currentPage) {
      const data = new FormData(form);
      const params = new URLSearchParams();
      for (const [key, value] of data.entries()) {
        const clean = String(value).trim();
        if (clean) params.set(key, clean);
      }
      params.set("page", String(page));
      params.set("per_page", String(pageSize));
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
    }

    async function runSearch(page = currentPage) {
      resultsEl.innerHTML = '<div class="empty">Searching local databases...</div>';
      paginationEl.innerHTML = "";
      const response = await fetch(`/api/search?${buildParams(page).toString()}`);
      const payload = await response.json();
      if (!response.ok) {
        resultsEl.innerHTML = `<div class="error">${esc(payload.error || "Search failed")}</div>`;
        return;
      }
      renderResults(payload);
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      currentPage = 1;
      runSearch(1);
    });
    resetBtn.addEventListener("click", () => {
      form.reset();
      syncSalaryInputsFromRange();
      currentPage = 1;
      runSearch(1);
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

    syncSalaryTrack();
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

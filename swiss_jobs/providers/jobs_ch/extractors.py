from __future__ import annotations

import html
import json
import re
from typing import Any

from swiss_jobs.core.models import VacancyFull


class ParseError(RuntimeError):
    """Raised when jobs.ch HTML does not contain the expected JS payload."""


def extract_js_object(text: str, marker: str) -> dict[str, Any]:
    marker_pos = text.find(marker)
    if marker_pos == -1:
        raise ParseError(f"Marker not found: {marker}")

    start = text.find("{", marker_pos)
    if start == -1:
        raise ParseError(f"JSON object not found after marker: {marker}")

    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : idx + 1])

    raise ParseError(f"Unclosed JSON object after marker: {marker}")


def get_results_bucket(init_state: dict[str, Any], mode: str) -> dict[str, Any]:
    vacancy = init_state.get("vacancy", {})
    results = vacancy.get("results", {})
    if mode == "new":
        return results.get("newVacancies") or {}
    return results.get("main") or {}


def parse_jobs_from_bucket(bucket: dict[str, Any], base_url: str) -> list[VacancyFull]:
    if not bucket:
        return []

    jobs: list[VacancyFull] = []
    for row in bucket.get("results", []):
        vacancy_id = row.get("id")
        if not vacancy_id:
            continue

        company = row.get("company") or {}
        jobs.append(
            VacancyFull(
                id=str(vacancy_id),
                title=str(row.get("title") or "").strip(),
                company=str(company.get("name") or "").strip(),
                place=str(row.get("place") or "").strip(),
                publication_date=row.get("publicationDate"),
                initial_publication_date=row.get("initialPublicationDate"),
                is_new=bool(row.get("isNew")),
                url=f"{base_url}/en/vacancies/detail/{vacancy_id}/",
                raw=dict(row),
            )
        )
    return jobs


def extract_job_posting_schema(page_html: str) -> dict[str, Any] | None:
    pattern = re.compile(
        r'<script type="application/ld\+json">(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(page_html):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            if item_type == "JobPosting":
                return item
            if isinstance(item_type, list) and "JobPosting" in item_type:
                return item
    return None


def extract_salary_payload(page_html: str) -> dict[str, Any] | None:
    candidates = _find_salary_candidates(page_html)
    for candidate in candidates:
        payload = _parse_salary_text(candidate)
        if payload:
            return payload
    return None


def html_to_text(value: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", value)
    text = re.sub(r"(?i)</(p|div|h1|h2|h3|h4|h5|h6|li|ul|ol)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _find_salary_candidates(page_html: str) -> list[str]:
    patterns = [
        re.compile(
            r'<li[^>]*data-cy=["\'][^"\']*salary[^"\']*["\'][^>]*>(.*?)</li>',
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r'<div[^>]*data-cy=["\'][^"\']*salary[^"\']*["\'][^>]*>(.*?)</div>',
            re.IGNORECASE | re.DOTALL,
        ),
    ]
    result: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in pattern.finditer(page_html):
            text = html_to_text(match.group(1))
            if not text:
                continue
            normalized = " ".join(text.split())
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
    return result


def _parse_salary_text(value: str) -> dict[str, Any] | None:
    compact = " ".join(value.split())
    match = re.search(
        r"(?P<currency>CHF|EUR|USD|GBP)\s*"
        r"(?P<minimum>\d[\d\s'.,]*)\s*(?:-|–|—)\s*"
        r"(?P<maximum>\d[\d\s'.,]*)"
        r"(?:\s*/\s*(?P<unit>year|month|hour))?",
        compact,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    currency = str(match.group("currency") or "").upper()
    minimum = _parse_salary_number(match.group("minimum"))
    maximum = _parse_salary_number(match.group("maximum"))
    if minimum is None or maximum is None:
        return None

    unit_text = str(match.group("unit") or "").strip().lower()
    unit = _normalize_salary_unit(unit_text)
    salary_text = _format_salary_text(currency, minimum, maximum, unit)
    payload: dict[str, Any] = {
        "salary": {
            "currency": currency,
            "range": {
                "minValue": minimum,
                "maxValue": maximum,
            },
        },
        "salary_text": salary_text,
    }
    if unit:
        payload["salary"]["unit"] = unit
    return payload


def _parse_salary_number(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return None
    return int(digits)


def _normalize_salary_unit(value: str) -> str | None:
    mapping = {
        "year": "YEAR",
        "month": "MONTH",
        "hour": "HOUR",
    }
    return mapping.get(value) if value else None


def _format_salary_text(currency: str, minimum: int, maximum: int, unit: str | None) -> str:
    unit_suffix = f" / {unit.lower()}" if unit else ""
    return f"{currency} {minimum}-{maximum}{unit_suffix}".strip()

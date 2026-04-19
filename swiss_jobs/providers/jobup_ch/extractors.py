from __future__ import annotations

import re
from math import ceil
from typing import Any

from swiss_jobs.core.models import VacancyFull

from ..jobs_ch.extractors import (
    ParseError,
    extract_job_posting_schema,
    extract_js_object,
    html_to_text,
)

BASE_PAGE_SIZE = 20


def parse_jobs_from_search_page(
    page_html: str,
    *,
    base_url: str,
    mode: str,
) -> tuple[list[VacancyFull], int | None]:
    init_state = extract_js_object(page_html, "__INIT__ = ")
    bucket = _get_results_bucket(init_state, mode=mode)
    jobs = _parse_jobs_from_bucket(bucket, base_url=base_url)
    return jobs, _extract_total_pages(bucket, page_html=page_html, jobs_count=len(jobs))


def extract_detail_payload(page_html: str) -> dict[str, Any]:
    schema = extract_job_posting_schema(page_html)
    salary_payload = _extract_salary_payload(page_html)
    description_html = ""
    if isinstance(schema, dict):
        raw_description = schema.get("description")
        if isinstance(raw_description, str):
            description_html = raw_description.strip()
        if salary_payload and "baseSalary" not in schema:
            salary = salary_payload.get("salary")
            if isinstance(salary, dict):
                base_salary: dict[str, Any] = {
                    "currency": str(salary.get("currency") or "").strip(),
                }
                salary_range = salary.get("range")
                value: dict[str, Any] = {}
                if isinstance(salary_range, dict):
                    if salary_range.get("minValue") is not None:
                        value["minValue"] = salary_range.get("minValue")
                    if salary_range.get("maxValue") is not None:
                        value["maxValue"] = salary_range.get("maxValue")
                if salary.get("unit"):
                    value["unitText"] = str(salary.get("unit")).strip()
                if base_salary.get("currency") and value:
                    base_salary["value"] = value
                    schema["baseSalary"] = base_salary

    if not description_html:
        raise ParseError("JobPosting schema not found on jobup detail page")

    return {
        "job_posting_schema": schema,
        "description_html": description_html,
        "description_text": html_to_text(description_html),
        "salary": salary_payload.get("salary") if salary_payload else None,
        "salary_text": salary_payload.get("salary_text") if salary_payload else None,
    }


def _get_results_bucket(init_state: dict[str, Any], *, mode: str) -> dict[str, Any]:
    vacancy = init_state.get("vacancy")
    if not isinstance(vacancy, dict):
        raise ParseError("jobup init state does not contain vacancy results")

    results = vacancy.get("results")
    if not isinstance(results, dict):
        raise ParseError("jobup init state does not contain results buckets")

    if mode == "new":
        bucket = results.get("newVacancies")
    else:
        bucket = results.get("main")

    if not isinstance(bucket, dict):
        raise ParseError(f"jobup results bucket is missing for mode={mode!r}")
    return bucket


def _parse_jobs_from_bucket(bucket: dict[str, Any], *, base_url: str) -> list[VacancyFull]:
    rows = bucket.get("results")
    if not isinstance(rows, list):
        return []

    jobs: list[VacancyFull] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        vacancy_id = str(row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        if not vacancy_id or not title:
            continue

        company = row.get("company")
        company_name = ""
        if isinstance(company, dict):
            company_name = str(company.get("name") or "").strip()

        raw = dict(row)
        workload = _format_workload(row.get("employmentGrades"))
        if workload:
            raw["workload"] = workload

        salary = _format_salary(row.get("salary"))
        if salary:
            raw["salaryText"] = salary

        jobs.append(
            VacancyFull(
                id=vacancy_id,
                title=title,
                company=company_name,
                place=str(row.get("place") or "").strip(),
                publication_date=_string_or_none(row.get("publicationDate")),
                initial_publication_date=_string_or_none(row.get("initialPublicationDate")),
                is_new=bool(row.get("isNew")),
                url=f"{base_url}/en/jobs/detail/{vacancy_id}/",
                raw=raw,
                source="jobup.ch",
            )
        )
    return jobs


def _extract_total_pages(bucket: dict[str, Any], *, page_html: str, jobs_count: int) -> int | None:
    meta = bucket.get("meta")
    if isinstance(meta, dict):
        value = meta.get("numPages")
        if isinstance(value, int) and value > 0:
            return value

    value = bucket.get("numPages")
    if isinstance(value, int) and value > 0:
        return value

    total_hits = _extract_total_hits_from_title(page_html)
    if total_hits is not None and total_hits > 0:
        return max(1, ceil(total_hits / BASE_PAGE_SIZE))

    if jobs_count < BASE_PAGE_SIZE:
        return 1
    return None


def _extract_total_hits_from_title(page_html: str) -> int | None:
    title_start = page_html.find("<title>")
    title_end = page_html.find("</title>", title_start + 7)
    if title_start == -1 or title_end == -1:
        return None

    title = page_html[title_start + 7 : title_end]
    digits = []
    current = ""
    for char in title:
        if char.isdigit():
            current += char
        elif current:
            digits.append(current)
            current = ""
    if current:
        digits.append(current)

    if not digits:
        return None
    try:
        return int(digits[0])
    except ValueError:
        return None


def _format_workload(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return ""
    normalized = [item for item in value if isinstance(item, int)]
    if not normalized:
        return ""
    low = min(normalized)
    high = max(normalized)
    if low == high:
        return f"{low}%"
    return f"{low}% - {high}%"


def _format_salary(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    currency = str(value.get("currency") or "").strip()
    unit = str(value.get("unit") or "").strip()
    salary_range = value.get("range")
    if not isinstance(salary_range, dict):
        return ""
    minimum = salary_range.get("minValue")
    maximum = salary_range.get("maxValue")
    if not isinstance(minimum, (int, float)) or not isinstance(maximum, (int, float)):
        return ""
    unit_suffix = f" / {unit.lower()}" if unit else ""
    currency_prefix = f"{currency} " if currency else ""
    if minimum == maximum:
        return f"{currency_prefix}{int(minimum)}{unit_suffix}".strip()
    return f"{currency_prefix}{int(minimum)} - {int(maximum)}{unit_suffix}".strip()


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_salary_payload(page_html: str) -> dict[str, Any] | None:
    match = re.search(
        r"(?P<currency>CHF|EUR|USD|GBP)\s*"
        r"(?P<minimum>\d[\d\s'.,]*)\s*(?:-|–|—)\s*"
        r"(?P<maximum>\d[\d\s'.,]*)\s*/\s*"
        r"(?P<unit>an|year|jahr|mois|month|monat|heure|hour|stunde)",
        page_html,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    currency = str(match.group("currency") or "").upper()
    minimum = _parse_salary_number(match.group("minimum"))
    maximum = _parse_salary_number(match.group("maximum"))
    if minimum is None or maximum is None:
        return None

    unit = _normalize_salary_unit(str(match.group("unit") or "").strip().lower())
    salary: dict[str, Any] = {
        "currency": currency,
        "range": {
            "minValue": minimum,
            "maxValue": maximum,
        },
    }
    if unit:
        salary["unit"] = unit

    return {
        "salary": salary,
        "salary_text": _format_salary_text(currency, minimum, maximum, unit),
    }


def _parse_salary_number(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return None
    return int(digits)


def _normalize_salary_unit(value: str) -> str | None:
    mapping = {
        "an": "YEAR",
        "year": "YEAR",
        "jahr": "YEAR",
        "mois": "MONTH",
        "month": "MONTH",
        "monat": "MONTH",
        "heure": "HOUR",
        "hour": "HOUR",
        "stunde": "HOUR",
    }
    return mapping.get(value) if value else None


def _format_salary_text(currency: str, minimum: int, maximum: int, unit: str | None) -> str:
    unit_suffix = f" / {unit.lower()}" if unit else ""
    return f"{currency} {minimum}-{maximum}{unit_suffix}".strip()

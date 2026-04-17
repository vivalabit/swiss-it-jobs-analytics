from __future__ import annotations

import html
from datetime import UTC, datetime
import json
import math
import re
import unicodedata
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin

from swiss_jobs.core.models import VacancyFull

from ..jobs_ch.extractors import ParseError, extract_js_object, html_to_text

PAGE_SIZE = 20
BASE_CURRENCY = "CHF"


def parse_jobs_from_feed(
    payload: Sequence[Mapping[str, Any]],
    *,
    base_url: str,
    mode: str,
    term: str,
    location: str,
    max_pages: int,
) -> tuple[list[VacancyFull], int]:
    active_rows = [dict(item) for item in payload if isinstance(item, Mapping) and _is_active_job(item)]
    active_rows.sort(key=_sort_key, reverse=True)

    filtered_rows: list[dict[str, Any]] = []
    for row in active_rows:
        if mode == "search" and not _matches_term(row, term):
            continue
        if mode == "search" and not _matches_location(row, location):
            continue
        filtered_rows.append(row)

    total_pages = max(1, math.ceil(len(filtered_rows) / PAGE_SIZE)) if filtered_rows else 1
    if max_pages > 0:
        filtered_rows = filtered_rows[: max_pages * PAGE_SIZE]

    jobs = [_parse_job_row(row, base_url=base_url) for row in filtered_rows]
    return jobs, total_pages


def extract_detail_payload(page_html: str, *, page_url: str = "") -> dict[str, Any]:
    try:
        detail = extract_js_object(page_html, "window.__detailedJob=")
    except ParseError as exc:
        raise ParseError("SwissDevJobs detail page does not contain window.__detailedJob payload") from exc

    if not detail or not isinstance(detail, dict):
        raise ParseError("SwissDevJobs detail payload is empty")

    description_html = _build_description_html(detail)
    job_posting_schema = _build_job_posting_schema(detail, description_html=description_html, page_url=page_url)
    detail_attributes = _build_detail_attributes(detail)
    return {
        "detail_payload": detail,
        "job_posting_schema": job_posting_schema,
        "description_html": description_html,
        "description_text": html_to_text(description_html),
        "detail_attributes": detail_attributes,
    }


def _parse_job_row(row: Mapping[str, Any], *, base_url: str) -> VacancyFull:
    vacancy_id = str(row.get("_id") or "").strip()
    title = str(row.get("name") or "").strip()
    if not vacancy_id or not title:
        raise ParseError("SwissDevJobs feed row is missing _id or name")

    job_slug = str(row.get("jobUrl") or "").strip()
    url = urljoin(f"{base_url}/", f"jobs/{job_slug}") if job_slug else base_url
    place = _build_place(row)
    publication_date = _string_or_none(row.get("activeFrom"))
    raw = dict(row)

    technologies = _coerce_string_list(row.get("technologies"))
    filter_tags = _coerce_string_list(row.get("filterTags"))
    if technologies:
        raw["technologies"] = technologies
    if filter_tags:
        raw["filterTags"] = filter_tags
        raw["listingTags"] = filter_tags

    salary = _build_salary_payload(row)
    if salary:
        raw["salary"] = salary
        raw["salaryText"] = _format_salary_text(salary)

    workload = _extract_workload_from_text(title)
    if workload:
        raw["workload"] = workload

    job_type = _string_or_none(row.get("jobType"))
    if job_type:
        raw["employmentType"] = job_type
        raw["jobType"] = job_type

    workplace = _string_or_none(row.get("workplace"))
    if workplace:
        raw["workplace"] = workplace

    return VacancyFull(
        id=vacancy_id,
        title=title,
        company=str(row.get("company") or "").strip(),
        place=place,
        publication_date=publication_date,
        initial_publication_date=publication_date,
        is_new=_is_recent(publication_date),
        url=url,
        raw=raw,
        source="swissdevjobs.ch",
    )


def _build_description_html(detail: Mapping[str, Any]) -> str:
    sections: list[str] = []
    details = _build_fact_items(detail)
    if details:
        sections.append(_build_list_section("Listing Details", details))

    technologies = _coerce_string_list(detail.get("technologies"))
    if technologies:
        sections.append(_build_list_section("Technologies", technologies))

    requirements = _build_bullets(detail.get("requirementsMustTextArea"))
    if requirements:
        sections.append(_build_list_section("Requirements", requirements))

    responsibilities = _build_bullets(detail.get("responsibilitiesTextArea"))
    if responsibilities:
        sections.append(_build_list_section("Responsibilities", responsibilities))

    methodology = _build_methodology_items(detail)
    if methodology:
        sections.append(_build_list_section("Methodology", methodology))

    description = _build_paragraphs(detail.get("description"))
    if description:
        sections.append(_build_paragraph_section("Description", description))

    perks = _coerce_string_list(detail.get("perkKeys"))
    if perks:
        sections.append(_build_list_section("Benefits", perks))

    return "".join(sections).strip()


def _build_job_posting_schema(
    detail: Mapping[str, Any],
    *,
    description_html: str,
    page_url: str,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": str(detail.get("name") or "").strip(),
        "description": description_html,
    }

    if page_url:
        schema["url"] = page_url

    date_posted = _string_or_none(detail.get("activeFrom"))
    if date_posted:
        schema["datePosted"] = date_posted

    employment_type = _string_or_none(detail.get("jobType"))
    if employment_type:
        schema["employmentType"] = employment_type

    workplace = _string_or_none(detail.get("workplace"))
    if workplace == "remote":
        schema["jobLocationType"] = "TELECOMMUTE"

    organization = {
        "@type": "Organization",
        "name": str(detail.get("company") or "").strip(),
    }
    company_website = _normalize_website(detail.get("companyWebsiteLink"))
    if company_website:
        organization["sameAs"] = company_website
    logo_img = _string_or_none(detail.get("logoImg"))
    if logo_img:
        organization["logo"] = f"https://static.swissdevjobs.ch/logo-images/{logo_img}"
    schema["hiringOrganization"] = organization

    job_location = _build_job_location(detail)
    if job_location:
        schema["jobLocation"] = job_location

    salary = _build_salary_payload(detail)
    if salary:
        base_salary: dict[str, Any] = {
            "@type": "MonetaryAmount",
            "currency": str(salary.get("currency") or BASE_CURRENCY),
        }
        value: dict[str, Any] = {}
        salary_range = salary.get("range")
        if isinstance(salary_range, Mapping):
            if salary_range.get("minValue") is not None:
                value["minValue"] = salary_range.get("minValue")
            if salary_range.get("maxValue") is not None:
                value["maxValue"] = salary_range.get("maxValue")
            unit = _string_or_none(salary.get("unit"))
            if unit:
                value["unitText"] = unit
        if value:
            base_salary["value"] = value
        schema["baseSalary"] = base_salary

    occupational_categories = [
        value
        for value in (
            _string_or_none(detail.get("techCategory")),
            _string_or_none(detail.get("metaCategory")),
        )
        if value
    ]
    if occupational_categories:
        schema["occupationalCategory"] = occupational_categories

    return schema


def _build_detail_attributes(detail: Mapping[str, Any]) -> dict[str, Any]:
    attributes: dict[str, Any] = {}

    for source_key, output_key in (
        ("activeFrom", "publicationDate"),
        ("jobType", "employmentTypeText"),
        ("workplace", "workplace"),
        ("language", "language"),
        ("candidateContactWay", "candidateContactWay"),
        ("hasVisaSponsorship", "visaSponsorship"),
        ("companyType", "companyType"),
        ("companySize", "companySize"),
        ("cityCategory", "cityCategory"),
        ("actualCity", "actualCity"),
    ):
        value = detail.get(source_key)
        if isinstance(value, str) and value.strip():
            attributes[output_key] = value.strip()

    salary = _build_salary_payload(detail)
    if salary:
        attributes["salary"] = salary
        attributes["salaryText"] = _format_salary_text(salary)

    technologies = _coerce_string_list(detail.get("technologies"))
    if technologies:
        attributes["technologies"] = technologies

    filter_tags = _coerce_string_list(detail.get("filterTags"))
    if filter_tags:
        attributes["listingTags"] = filter_tags

    workload = _extract_workload_from_text(str(detail.get("name") or ""))
    if workload:
        attributes["workload"] = workload

    return attributes


def _build_job_location(detail: Mapping[str, Any]) -> dict[str, Any] | None:
    city = _string_or_none(detail.get("actualCity")) or _string_or_none(detail.get("cityCategory"))
    if not city:
        return None

    locality, region = _split_city_region(city)
    address = {
        "@type": "PostalAddress",
        "streetAddress": _string_or_none(detail.get("address")) or "",
        "addressLocality": locality,
        "postalCode": _string_or_none(detail.get("postalCode")) or "",
        "addressRegion": region,
        "addressCountry": "CH",
    }
    cleaned_address = {key: value for key, value in address.items() if value}
    if not cleaned_address:
        return None
    return {
        "@type": "Place",
        "address": cleaned_address,
    }


def _build_salary_payload(data: Mapping[str, Any]) -> dict[str, Any] | None:
    annual_from = data.get("annualSalaryFrom")
    annual_to = data.get("annualSalaryTo")
    contract_from = data.get("contractRateFrom")
    contract_to = data.get("contractRateTo")
    contract_rate_type = _string_or_none(data.get("contractRateType"))

    if isinstance(annual_from, (int, float)) and isinstance(annual_to, (int, float)):
        return {
            "currency": BASE_CURRENCY,
            "unit": "YEAR",
            "range": {
                "minValue": int(annual_from),
                "maxValue": int(annual_to),
            },
        }

    if isinstance(contract_from, (int, float)) and isinstance(contract_to, (int, float)):
        unit = "HOUR" if contract_rate_type == "hourly" else (contract_rate_type or "CONTRACT")
        return {
            "currency": BASE_CURRENCY,
            "unit": unit.upper(),
            "range": {
                "minValue": int(contract_from),
                "maxValue": int(contract_to),
            },
        }

    return None


def _format_salary_text(salary: Mapping[str, Any]) -> str:
    currency = str(salary.get("currency") or BASE_CURRENCY).strip()
    unit = str(salary.get("unit") or "").strip().lower()
    salary_range = salary.get("range")
    if not isinstance(salary_range, Mapping):
        return currency

    minimum = salary_range.get("minValue")
    maximum = salary_range.get("maxValue")
    suffix = f" / {unit}" if unit else ""
    if minimum == maximum:
        return f"{currency} {int(minimum)}{suffix}".strip()
    return f"{currency} {int(minimum)} - {int(maximum)}{suffix}".strip()


def _build_fact_items(detail: Mapping[str, Any]) -> list[str]:
    items: list[str] = []
    for label, value in (
        ("Workplace", _string_or_none(detail.get("workplace"))),
        ("Language", _string_or_none(detail.get("language"))),
        ("Company type", _string_or_none(detail.get("companyType"))),
        ("Company size", _string_or_none(detail.get("companySize"))),
        ("Visa sponsorship", _string_or_none(detail.get("hasVisaSponsorship"))),
        ("Contact way", _string_or_none(detail.get("candidateContactWay"))),
        ("Salary", _format_salary_text(_build_salary_payload(detail) or {})),
    ):
        if value:
            items.append(f"{label}: {value}")
    return items


def _build_methodology_items(detail: Mapping[str, Any]) -> list[str]:
    items: list[str] = []
    for key, label in (
        ("metScrum", "Scrum"),
        ("metCodeReviews", "Code Reviews"),
        ("metPairProgramm", "Pair Programming"),
        ("metUnitTests", "Unit Tests"),
        ("metIntegrationTests", "Integration Tests"),
        ("metBuildServer", "CI / CD Build Server"),
        ("metStaticCodeAnalysis", "Static Code Analysis"),
        ("metVersionControl", "Version Control"),
        ("metTesters", "Testers"),
        ("metTimeTracking", "Time Tracking"),
    ):
        if detail.get(key) is True:
            items.append(label)
    return items


def _build_bullets(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    rows = [line.strip() for line in value.splitlines()]
    return [row.lstrip("-").strip() for row in rows if row.strip()]


def _build_paragraphs(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", value) if chunk.strip()]
    return chunks


def _build_list_section(title: str, items: Sequence[str]) -> str:
    if not items:
        return ""
    rows = "".join(f"<li>{html.escape(item)}</li>" for item in items if item)
    if not rows:
        return ""
    return f"<h2>{html.escape(title)}</h2><ul>{rows}</ul>"


def _build_paragraph_section(title: str, paragraphs: Sequence[str]) -> str:
    if not paragraphs:
        return ""
    rows = "".join(f"<p>{html.escape(item)}</p>" for item in paragraphs if item)
    if not rows:
        return ""
    return f"<h2>{html.escape(title)}</h2>{rows}"


def _matches_term(row: Mapping[str, Any], term: str) -> bool:
    normalized_term = _normalize_text(term)
    if not normalized_term:
        return True
    haystack = " ".join(
        part
        for part in (
            _normalize_text(row.get("name")),
            _normalize_text(row.get("techCategory")),
            _normalize_text(row.get("metaCategory")),
            " ".join(_normalize_text(item) for item in _coerce_string_list(row.get("technologies"))),
            " ".join(_normalize_text(item) for item in _coerce_string_list(row.get("filterTags"))),
        )
        if part
    )
    return normalized_term in haystack


def _matches_location(row: Mapping[str, Any], location: str) -> bool:
    normalized_location = _normalize_text(location)
    if not normalized_location:
        return True
    haystack = " ".join(
        part
        for part in (
            _normalize_text(row.get("actualCity")),
            _normalize_text(row.get("cityCategory")),
            _normalize_text(row.get("address")),
        )
        if part
    )
    return normalized_location in haystack


def _build_place(row: Mapping[str, Any]) -> str:
    city = _string_or_none(row.get("actualCity")) or _string_or_none(row.get("cityCategory")) or ""
    return city


def _extract_workload_from_text(value: str) -> str:
    percentages = [int(item) for item in re.findall(r"(\d{1,3})(?=\s*(?:-|to)\s*\d{1,3}\s*%|\s*%)", value)]
    if not percentages:
        return ""
    low = min(percentages)
    high = max(percentages)
    if low == high:
        return f"{low}%"
    return f"{low}% - {high}%"


def _split_city_region(value: str) -> tuple[str, str]:
    cleaned = str(value or "").strip()
    if "," in cleaned:
        left, right = [part.strip() for part in cleaned.split(",", 1)]
        return left or cleaned, right
    return cleaned, ""


def _normalize_website(value: Any) -> str:
    raw = _string_or_none(value)
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    return f"https://{raw}"


def _is_active_job(row: Mapping[str, Any]) -> bool:
    if bool(row.get("isPaused")):
        return False
    deactivated_on = row.get("deactivatedOn")
    if isinstance(deactivated_on, str) and deactivated_on.strip():
        return False
    return True


def _sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    active_from = _string_or_none(row.get("activeFrom")) or ""
    vacancy_id = str(row.get("_id") or "")
    return active_from, vacancy_id


def _is_recent(value: str | None, *, hours: int = 48) -> bool:
    if not value:
        return False
    try:
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    now = datetime.now(tz=published.tzinfo)
    return (now - published).total_seconds() <= hours * 3600


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        clean = value.strip()
        return [clean] if clean else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                result.append(item.strip())
        return result
    return []


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())

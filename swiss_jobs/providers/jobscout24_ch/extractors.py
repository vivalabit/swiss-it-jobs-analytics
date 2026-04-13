from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from swiss_jobs.core.models import VacancyFull

from ..jobs_ch.extractors import extract_job_posting_schema, html_to_text


class ParseError(RuntimeError):
    """Raised when JobScout24 HTML does not contain the expected vacancy payload."""


def parse_jobs_from_search_page(page_html: str, *, base_url: str) -> tuple[list[VacancyFull], int | None]:
    jobs: list[VacancyFull] = []
    segments = _extract_job_segments(page_html)
    for segment in segments:
        vacancy = _parse_job_segment(segment, base_url=base_url)
        if vacancy is not None:
            jobs.append(vacancy)
    return jobs, extract_total_pages(page_html)


def extract_total_pages(page_html: str) -> int | None:
    match = re.search(r"Page\s+\d+\s*/\s*(\d+)", page_html, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    return value if value > 0 else None


def extract_detail_payload(page_html: str) -> dict[str, Any]:
    schema = extract_job_posting_schema(page_html)
    description_html = ""
    if isinstance(schema, dict):
        raw_description = schema.get("description")
        if isinstance(raw_description, str):
            description_html = raw_description.strip()

    if not description_html:
        description_html = _extract_job_description_html(page_html)

    detail_attributes = _extract_detail_attributes(page_html)
    return {
        "job_posting_schema": schema,
        "description_html": description_html,
        "description_text": html_to_text(description_html) if description_html else "",
        "detail_attributes": detail_attributes,
    }


def _extract_job_segments(page_html: str) -> list[str]:
    markers = list(re.finditer(r'<li class="job-list-item\b', page_html))
    if not markers:
        return []

    end_boundary = page_html.find('<div class="pagination">')
    if end_boundary == -1:
        end_boundary = len(page_html)

    segments: list[str] = []
    for index, marker in enumerate(markers):
        start = marker.start()
        next_start = markers[index + 1].start() if index + 1 < len(markers) else end_boundary
        segments.append(page_html[start:next_start])
    return segments


def _parse_job_segment(segment: str, *, base_url: str) -> VacancyFull | None:
    job_id = _search(segment, r'data-job-id="([^"]+)"')
    detail_url = _search(segment, r'data-job-detail-url="([^"]+)"')
    if not job_id or not detail_url:
        return None

    title = _clean_html_text(
        _search(
            segment,
            r'<a[^>]+class="[^"]*\bjob-title\b[^"]*"[^>]*title="([^"]+)"',
        )
        or _search(
            segment,
            r'<a[^>]+class="[^"]*\bjob-title\b[^"]*"[^>]*>(.*?)</a>',
            flags=re.DOTALL,
        )
        or ""
    )
    if not title:
        return None

    attributes_html = _search(
        segment,
        r'<p class="job-attributes">(.*?)</p>',
        flags=re.DOTALL,
    ) or ""
    attributes = [
        _clean_html_text(match.group(1))
        for match in re.finditer(r"<span>(.*?)</span>", attributes_html, flags=re.DOTALL)
        if _clean_html_text(match.group(1))
    ]

    tags = [
        _clean_html_text(match.group(1))
        for match in re.finditer(
            r'<span class="tag tag-readonly(?: orange)?">(.*?)</span>',
            segment,
            flags=re.DOTALL,
        )
        if _clean_html_text(match.group(1))
    ]

    publication_date = _clean_html_text(
        _search(
            segment,
            r'<p class="job-date">\s*(.*?)\s*</p>',
            flags=re.DOTALL,
        )
        or ""
    )

    raw: dict[str, Any] = {
        "tags": tags,
    }
    workload = next((tag for tag in tags if "%" in tag), "")
    job_type = next((tag for tag in tags if "position" in tag.casefold()), "")
    if workload:
        raw["workload"] = workload
    if job_type:
        raw["employmentType"] = job_type
    return VacancyFull(
        id=job_id,
        title=title,
        company=attributes[0] if attributes else "",
        place=attributes[1] if len(attributes) > 1 else "",
        publication_date=publication_date or None,
        is_new=publication_date.casefold() == "new" if publication_date else False,
        url=urljoin(base_url, detail_url),
        raw=raw,
        source="jobscout24.ch",
    )


def _extract_job_description_html(page_html: str) -> str:
    match = re.search(
        r'<div class="job-description">\s*(?:<style.*?</style>)?(.*?)</div>\s*</div>',
        page_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _extract_detail_attributes(page_html: str) -> dict[str, str]:
    article_match = re.search(
        r'<article class="job-details"([^>]+)>',
        page_html,
        flags=re.DOTALL,
    )
    if not article_match:
        return {}

    attrs_block = article_match.group(1)
    result: dict[str, str] = {}
    for html_name, output_name in (
        ("data-pub-date", "publicationDate"),
        ("data-employment-grade", "employmentGrade"),
        ("data-employment-type", "employmentTypeText"),
        ("data-job-position", "jobPosition"),
        ("data-job-location", "jobLocationSlug"),
    ):
        value = _search(attrs_block, rf'{re.escape(html_name)}="([^"]*)"')
        if value:
            result[output_name] = value
    return result


def _search(text: str, pattern: str, *, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags=flags)
    if not match:
        return None
    return match.group(1)


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&#246;", "ö")
        .replace("&#252;", "ü")
        .replace("&#228;", "ä")
        .replace("&#233;", "é")
        .replace("&#39;", "'")
        .replace("&amp;", "&")
    )
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,\n\t")

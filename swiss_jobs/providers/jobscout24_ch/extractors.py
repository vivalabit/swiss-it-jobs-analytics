from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urljoin

from scrapling.parser import Selector

from swiss_jobs.core.models import VacancyFull

from ..jobs_ch.extractors import html_to_text


class ParseError(RuntimeError):
    """Raised when JobScout24 HTML does not contain the expected vacancy payload."""


def parse_jobs_from_search_page(page_html: str, *, base_url: str) -> tuple[list[VacancyFull], int | None]:
    document = Selector(page_html, url=base_url)
    jobs: list[VacancyFull] = []
    for segment in document.css("li.job-list-item"):
        vacancy = _parse_job_segment(segment, base_url=base_url)
        if vacancy is not None:
            jobs.append(vacancy)
    return jobs, extract_total_pages(page_html, document=document)


def extract_total_pages(page_html: str, *, document: Selector | None = None) -> int | None:
    selector = document or Selector(page_html)
    pagination = selector.css(".pagination .pages li::text").getall()
    match = re.search(
        r"Page\s+\d+\s*/\s*(\d+)",
        " ".join(_clean_html_text(text) for text in pagination),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    return value if value > 0 else None


def extract_detail_payload(page_html: str) -> dict[str, Any]:
    document = Selector(page_html)
    schema = _extract_job_posting_schema(document)
    description_html = ""
    if isinstance(schema, dict):
        raw_description = schema.get("description")
        if isinstance(raw_description, str):
            description_html = raw_description.strip()

    if not description_html:
        description_html = _extract_job_description_html(document)

    detail_attributes = _extract_detail_attributes(document)
    return {
        "job_posting_schema": schema,
        "description_html": description_html,
        "description_text": html_to_text(description_html) if description_html else "",
        "detail_attributes": detail_attributes,
    }


def _parse_job_segment(segment: Selector, *, base_url: str) -> VacancyFull | None:
    job_id = _clean_html_text(segment.attrib.get("data-job-id", ""))
    detail_url = _clean_html_text(segment.attrib.get("data-job-detail-url", ""))
    if not job_id or not detail_url:
        return None

    job_title = segment.css("a.job-title").first
    if job_title is None:
        return None

    title = _clean_html_text(job_title.attrib.get("title") or job_title.get_all_text())
    if not title:
        return None

    attributes = [
        cleaned
        for text in segment.css("p.job-attributes span::text").getall()
        if (cleaned := _clean_html_text(text))
    ]

    tags = [
        cleaned
        for text in segment.css(".job-tags .tag::text").getall()
        if (cleaned := _clean_html_text(text))
    ]

    job_date = segment.css("p.job-date").first
    publication_date = _clean_html_text(job_date.get_all_text() if job_date is not None else "")

    raw: dict[str, Any] = {
        "tags": tags,
    }
    if publication_date:
        raw["publicationDateText"] = publication_date
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


def _extract_job_posting_schema(document: Selector) -> dict[str, Any] | None:
    for raw_script in document.css('script[type="application/ld+json"]::text').getall():
        raw = raw_script.strip()
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


def _extract_job_description_html(document: Selector) -> str:
    description = document.css(".job-description").first
    if description is None:
        return ""

    content_blocks = [block.get() for block in description.css(":scope > :not(style)") if block.get().strip()]
    if content_blocks:
        return "".join(content_blocks).strip()

    return description.html_content.strip()


def _extract_detail_attributes(document: Selector) -> dict[str, str]:
    details = document.css("article.job-details").first
    if details is None:
        return {}

    result: dict[str, str] = {}
    for html_name, output_name in (
        ("data-pub-date", "publicationDate"),
        ("data-employment-grade", "employmentGrade"),
        ("data-employment-type", "employmentTypeText"),
        ("data-job-position", "jobPosition"),
        ("data-job-location", "jobLocationSlug"),
    ):
        value = _clean_html_text(details.attrib.get(html_name, ""))
        if value:
            result[output_name] = value
    return result


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = html.unescape(text.replace("&nbsp;", " "))
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,\n\t")

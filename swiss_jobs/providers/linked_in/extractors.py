from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from scrapling.parser import Selector

from swiss_jobs.core.models import VacancyFull
from swiss_jobs.providers.jobs_ch.extractors import html_to_text


class ParseError(RuntimeError):
    """Raised when LinkedIn HTML does not contain parseable vacancy cards."""


CARD_SELECTORS = (
    "li.jobs-search-results__list-item",
    "li.scaffold-layout__list-item",
    "li[data-occludable-job-id]",
    "div.job-card-container",
    "div.base-search-card",
)

TITLE_SELECTORS = (
    ".job-card-list__title",
    ".job-card-container__link",
    ".base-search-card__title",
    ".job-search-card__title",
    "a[href*='/jobs/view/']",
)

COMPANY_SELECTORS = (
    ".job-card-container__primary-description",
    ".artdeco-entity-lockup__subtitle",
    ".base-search-card__subtitle",
    ".job-search-card__subtitle",
    "a[href*='/company/']",
)

LOCATION_SELECTORS = (
    ".job-card-container__metadata-item",
    ".artdeco-entity-lockup__caption",
    ".base-search-card__metadata",
    ".job-search-card__location",
)


def parse_jobs_from_search_page(page_html: str, *, base_url: str) -> list[VacancyFull]:
    document = Selector(page_html, url=base_url)
    jobs: list[VacancyFull] = []
    seen: set[str] = set()

    for card in document.css(", ".join(CARD_SELECTORS)):
        vacancy = _parse_job_card(card, base_url=base_url)
        if vacancy is None or vacancy.id in seen:
            continue
        seen.add(vacancy.id)
        jobs.append(vacancy)

    if jobs:
        return jobs

    for link in document.css("a[href*='/jobs/view/']"):
        vacancy = _parse_job_link(link, base_url=base_url)
        if vacancy is None or vacancy.id in seen:
            continue
        seen.add(vacancy.id)
        jobs.append(vacancy)

    return jobs


def extract_detail_payload(page_html: str) -> dict[str, Any]:
    document = Selector(page_html)
    schema = _extract_job_posting_schema(page_html)
    description_html = ""
    if isinstance(schema, dict):
        raw_description = schema.get("description")
        if isinstance(raw_description, str):
            description_html = raw_description.strip()

    if not description_html:
        description_html = _extract_description_html(document)

    raw: dict[str, Any] = {}
    salary_text = _extract_salary_text(document)
    if salary_text:
        raw["salary_text"] = salary_text

    return {
        "job_posting_schema": schema,
        "description_html": description_html,
        "description_text": html_to_text(description_html) if description_html else "",
        **raw,
    }


def _parse_job_card(card: Selector, *, base_url: str) -> VacancyFull | None:
    link = _first_element(card, TITLE_SELECTORS)
    if link is None:
        link = _first_element(card, ("a[href*='/jobs/view/']",))
    if link is None:
        return None

    href = _clean_text(link.attrib.get("href", ""))
    vacancy_id = (
        _clean_text(card.attrib.get("data-occludable-job-id", ""))
        or _clean_text(card.attrib.get("data-job-id", ""))
        or _extract_job_id(href)
    )
    title = _node_label(link)
    if not title:
        title = _first_text(card, TITLE_SELECTORS)
    if not vacancy_id or not title:
        return None

    company = _first_text(card, COMPANY_SELECTORS)
    place = _first_text(card, LOCATION_SELECTORS)
    publication_date = _extract_publication_date(card)
    raw: dict[str, Any] = {}
    listed_at = _first_text(card, (".job-card-container__listed-time", ".job-search-card__listdate"))
    if listed_at:
        raw["listedAtText"] = listed_at

    return VacancyFull(
        id=vacancy_id,
        title=title,
        company=company,
        place=place,
        publication_date=publication_date,
        initial_publication_date=publication_date,
        is_new=_looks_new(listed_at or publication_date or ""),
        url=_normalize_job_url(href, vacancy_id=vacancy_id, base_url=base_url),
        raw=raw,
        source="linkedin.com",
    )


def _parse_job_link(link: Selector, *, base_url: str) -> VacancyFull | None:
    href = _clean_text(link.attrib.get("href", ""))
    vacancy_id = _extract_job_id(href)
    title = _node_label(link)
    if not vacancy_id or not title:
        return None
    return VacancyFull(
        id=vacancy_id,
        title=title,
        url=_normalize_job_url(href, vacancy_id=vacancy_id, base_url=base_url),
        raw={},
        source="linkedin.com",
    )


def _extract_job_posting_schema(page_html: str) -> dict[str, Any] | None:
    pattern = re.compile(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(page_html):
        raw = html.unescape(match.group(1).strip())
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for item in _flatten_jsonld(parsed):
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            if item_type == "JobPosting":
                return item
            if isinstance(item_type, list) and "JobPosting" in item_type:
                return item
    return None


def _flatten_jsonld(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            return graph
        return [value]
    return []


def _extract_description_html(document: Selector) -> str:
    for selector in (
        ".jobs-description__content",
        ".jobs-box__html-content",
        ".description__text",
        "section.description",
    ):
        node = document.css(selector).first
        if node is not None:
            content = node.html_content.strip()
            if content:
                return content
    return ""


def _extract_salary_text(document: Selector) -> str:
    for node in document.css(".jobs-unified-top-card__job-insight"):
        text = _node_label(node)
        lowered = text.casefold()
        if "chf" in lowered or "salary" in lowered or "compensation" in lowered:
            return text
    return ""


def _first_element(node: Selector, selectors: tuple[str, ...]) -> Selector | None:
    for selector in selectors:
        match = node.css(selector).first
        if match is not None:
            return match
    return None


def _first_text(node: Selector, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        match = node.css(selector).first
        if match is None:
            continue
        text = _node_label(match)
        if text:
            return text
    return ""


def _node_label(node: Selector) -> str:
    for attr_name in ("aria-label", "title"):
        value = _clean_text(node.attrib.get(attr_name, ""))
        if value:
            return value
    return _clean_text(node.get_all_text())


def _extract_publication_date(card: Selector) -> str | None:
    time_node = card.css("time").first
    if time_node is not None:
        datetime_value = _clean_text(time_node.attrib.get("datetime", ""))
        if datetime_value:
            return datetime_value
        text_value = _node_label(time_node)
        if text_value:
            return text_value
    return None


def _extract_job_id(href: str) -> str:
    if not href:
        return ""
    match = re.search(r"/jobs/view/(?:[^/?#-]+-)?(?P<id>\d+)", href)
    if match:
        return match.group("id")
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    for key in ("currentJobId", "jobId"):
        values = params.get(key)
        if values and values[0].isdigit():
            return values[0]
    return ""


def _normalize_job_url(href: str, *, vacancy_id: str, base_url: str) -> str:
    if vacancy_id:
        return f"{base_url.rstrip('/')}/jobs/view/{vacancy_id}/"
    return urljoin(base_url, href)


def _looks_new(value: str) -> bool:
    text = value.casefold()
    return "new" in text or "hour" in text or "minute" in text


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = html.unescape(text.replace("&nbsp;", " "))
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,\n\t")

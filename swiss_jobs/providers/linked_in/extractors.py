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
    "div[data-job-id]",
    "div[data-view-name='job-card']",
    "div.job-card-container",
    "div.base-search-card",
)

TITLE_SELECTORS = (
    "a.job-card-list__title--link strong",
    "a.job-card-list__title--link",
    "a.job-card-container__link",
    "a[href*='/jobs/view/'] strong",
    ".base-search-card__title",
    ".job-search-card__title",
    ".artdeco-entity-lockup__title a",
    ".artdeco-entity-lockup__title",
    ".job-card-list__title",
    "a[href*='/jobs/view/']",
)

COMPANY_SELECTORS = (
    ".job-card-container__primary-description",
    ".job-card-container__company-name",
    ".artdeco-entity-lockup__subtitle",
    ".artdeco-entity-lockup__subtitle span",
    ".base-search-card__subtitle",
    ".job-search-card__subtitle",
    "a[href*='/company/']",
)

LOCATION_SELECTORS = (
    ".job-card-container__metadata-item",
    ".job-card-container__metadata-wrapper li",
    ".artdeco-entity-lockup__caption",
    ".artdeco-entity-lockup__caption span",
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
    detail_root = _detail_root(document)
    schema = _extract_job_posting_schema(page_html)
    description_html = ""
    if isinstance(schema, dict):
        raw_description = schema.get("description")
        if isinstance(raw_description, str):
            description_html = raw_description.strip()

    if not description_html:
        description_html = _extract_description_html(detail_root) or _extract_description_html(document)

    raw: dict[str, Any] = {}
    salary_text = _extract_salary_text(detail_root)
    if salary_text:
        raw["salary_text"] = salary_text
    posted_at_text = _extract_detail_posted_at(detail_root)
    if posted_at_text:
        raw["posted_at_text"] = posted_at_text
    detail_attributes = _extract_detail_attributes(detail_root)

    return {
        "job_posting_schema": schema,
        "description_html": description_html,
        "description_text": html_to_text(description_html) if description_html else "",
        "title": _extract_detail_title(detail_root),
        "company": _extract_detail_company(detail_root),
        "place": _extract_detail_location(detail_root),
        "detail_attributes": detail_attributes,
        **raw,
    }


def _parse_job_card(card: Selector, *, base_url: str) -> VacancyFull | None:
    link = _first_element(card, TITLE_SELECTORS)
    if link is None:
        link = _first_element(card, ("a[href*='/jobs/view/']",))
    if link is None:
        return None

    href = _clean_text(link.attrib.get("href", ""))
    linkedin_job_id = (
        _clean_text(card.attrib.get("data-occludable-job-id", ""))
        or _clean_text(card.attrib.get("data-job-id", ""))
        or _clean_text(card.attrib.get("data-entity-urn", "")).rsplit(":", 1)[-1]
        or _extract_job_id(href)
    )
    title = _clean_title(_node_label(link))
    if not title:
        title = _clean_title(_first_text(card, TITLE_SELECTORS))
    if not linkedin_job_id or not title:
        return None

    company = _clean_company(_first_text(card, COMPANY_SELECTORS))
    place = _clean_location(_first_text(card, LOCATION_SELECTORS))
    publication_date = _extract_publication_date(card)
    raw: dict[str, Any] = {
        "linkedinJobId": linkedin_job_id,
        "cardText": _node_label(card),
    }
    entity_urn = _clean_text(card.attrib.get("data-entity-urn", ""))
    if entity_urn:
        raw["entityUrn"] = entity_urn
    metadata_items = _extract_metadata_items(card)
    if metadata_items:
        raw["metadataItems"] = metadata_items
    listed_at = _first_text(card, (".job-card-container__listed-time", ".job-search-card__listdate"))
    if listed_at:
        raw["listedAtText"] = listed_at
    if _contains_text(card, ("easy apply", "простая подача заявки")):
        raw["easyApply"] = True
    if _contains_text(card, ("promoted", "продвигается")):
        raw["promoted"] = True
    if _contains_text(card, ("actively reviewing", "активное рассмотрение")):
        raw["activelyReviewing"] = True

    return VacancyFull(
        id=_normalize_vacancy_id(linkedin_job_id),
        title=title,
        company=company,
        place=place,
        publication_date=publication_date,
        initial_publication_date=publication_date,
        is_new=_looks_new(listed_at or publication_date or ""),
        url=_normalize_job_url(href, linkedin_job_id=linkedin_job_id, base_url=base_url),
        raw=raw,
        source="linkedin.com",
    )


def _parse_job_link(link: Selector, *, base_url: str) -> VacancyFull | None:
    href = _clean_text(link.attrib.get("href", ""))
    linkedin_job_id = _extract_job_id(href)
    title = _clean_title(_node_label(link))
    if not linkedin_job_id or not title:
        return None
    return VacancyFull(
        id=_normalize_vacancy_id(linkedin_job_id),
        title=title,
        url=_normalize_job_url(href, linkedin_job_id=linkedin_job_id, base_url=base_url),
        raw={"linkedinJobId": linkedin_job_id},
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


def _detail_root(document: Selector) -> Selector:
    for selector in (
        ".jobs-search__job-details--container",
        ".scaffold-layout__detail",
        ".jobs-details",
        ".job-view-layout",
        ".job-details-jobs-unified-top-card__container",
        ".jobs-unified-top-card",
    ):
        node = document.css(selector).first
        if node is not None:
            return node
    return document


def _extract_description_html(document: Selector) -> str:
    for selector in (
        ".jobs-description__content",
        ".jobs-box__html-content",
        ".jobs-description-content__text",
        ".jobs-description-content__text--stretch",
        ".jobs-description__container",
        "article.jobs-description__container",
        "#job-details",
        ".description__text",
        "section.description",
    ):
        node = document.css(selector).first
        if node is not None:
            content = node.html_content.strip()
            if content:
                return content
    return ""


def _extract_detail_title(document: Selector) -> str:
    return _first_text(
        document,
        (
            ".job-details-jobs-unified-top-card__job-title h1",
            ".jobs-unified-top-card__job-title",
            ".job-details-jobs-unified-top-card__job-title",
            ".jobs-details__main-content h1",
            "h1",
        ),
    )


def _extract_detail_company(document: Selector) -> str:
    return _first_text(
        document,
        (
            ".job-details-jobs-unified-top-card__company-name a",
            ".jobs-unified-top-card__company-name",
            ".job-details-jobs-unified-top-card__company-name",
            ".jobs-unified-top-card__company-name a",
            "a[href*='/company/']",
        ),
    )


def _extract_detail_location(document: Selector) -> str:
    text = _first_text(
        document,
        (
            ".jobs-unified-top-card__primary-description-without-tagline",
            ".job-details-jobs-unified-top-card__primary-description-container",
            ".job-details-jobs-unified-top-card__primary-description",
            ".jobs-unified-top-card__primary-description",
            ".jobs-unified-top-card__bullet",
        ),
    )
    if " · " in text:
        parts = [part.strip() for part in text.split(" · ") if part.strip()]
        company = _extract_detail_company(document).casefold()
        for part in parts:
            if company and part.casefold() == company:
                continue
            if not _looks_like_non_location_detail(part):
                return _clean_location(part)
        return _clean_location(parts[0]) if parts else ""
    return _clean_location(text)


def _extract_detail_attributes(document: Selector) -> dict[str, Any]:
    result: dict[str, Any] = {}
    insights = [
        text
        for node in document.css(
            ".jobs-unified-top-card__job-insight, "
            ".job-details-jobs-unified-top-card__job-insight, "
            ".job-details-preferences-and-skills__pill, "
            ".job-details-fit-level-preferences__pill, "
            ".jobs-unified-top-card__workplace-type, "
            ".jobs-unified-top-card__job-insight-view-model-secondary"
        )
        if (text := _node_label(node))
    ]
    if insights:
        result["insights"] = insights

    workplace = _first_matching(insights, ("remote", "hybrid", "on-site", "удаленная", "гибрид", "офис"))
    if workplace:
        result["workplace"] = workplace

    applicant_count = _first_matching(insights, ("applicant", "candidate", "кандидат"))
    if applicant_count:
        result["applicantCountText"] = applicant_count

    return result


def _extract_salary_text(document: Selector) -> str:
    for node in document.css(
        ".jobs-unified-top-card__job-insight, .job-details-jobs-unified-top-card__job-insight"
    ):
        text = _node_label(node)
        lowered = text.casefold()
        if "chf" in lowered or "salary" in lowered or "compensation" in lowered:
            return text
    return ""


def _extract_detail_posted_at(document: Selector) -> str:
    text = _first_text(
        document,
        (
            ".jobs-unified-top-card__primary-description-without-tagline",
            ".job-details-jobs-unified-top-card__primary-description-container",
            ".job-details-jobs-unified-top-card__primary-description",
            ".jobs-unified-top-card__primary-description",
        ),
    )
    if not text:
        return ""
    parts = [part.strip() for part in text.split(" · ") if part.strip()]
    for part in parts:
        if _looks_like_posted_at(part):
            return part
    return ""


def _extract_metadata_items(card: Selector) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    selectors = (
        ".job-card-container__metadata-item",
        ".job-card-container__footer-item",
        ".job-card-container__listed-time",
        ".job-card-list__footer-wrapper li",
        ".artdeco-entity-lockup__caption",
    )
    for selector in selectors:
        for node in card.css(selector):
            text = _node_label(node)
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
    return result


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


def _normalize_job_url(href: str, *, linkedin_job_id: str, base_url: str) -> str:
    if linkedin_job_id:
        return f"{base_url.rstrip('/')}/jobs/view/{linkedin_job_id}/"
    return urljoin(base_url, href)


def _normalize_vacancy_id(linkedin_job_id: str) -> str:
    return f"linkedin:{linkedin_job_id}"


def _looks_new(value: str) -> bool:
    text = value.casefold()
    return "new" in text or "hour" in text or "minute" in text


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = html.unescape(text.replace("&nbsp;", " "))
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,\n\t")


def _clean_title(value: str) -> str:
    title = _clean_text(value)
    title = re.sub(r"\s+with verification$", "", title, flags=re.IGNORECASE)
    return title.strip()


def _clean_company(value: str) -> str:
    company = _clean_text(value)
    company = re.sub(r"\s+with verification$", "", company, flags=re.IGNORECASE)
    return company.strip()


def _clean_location(value: str) -> str:
    location = _clean_text(value)
    location = re.sub(r"\s+Actively Hiring\b.*$", "", location, flags=re.IGNORECASE)
    location = re.sub(r"\s+Станьте\s+.*$", "", location, flags=re.IGNORECASE)
    location = re.sub(r"\s+\d+\s+(minute|hour|day|week|month|year)s?\s+ago\b.*$", "", location, flags=re.IGNORECASE)
    location = re.sub(
        r"\s+\d+\s+(минут[а-я]*|час[а-я]*|дн[яеё][а-я]*|недел[яиюь][а-я]*|месяц[а-я]*|год[а-я]*)\s+назад\b.*$",
        "",
        location,
        flags=re.IGNORECASE,
    )
    return location.strip(" ,")


def _looks_like_non_location_detail(value: str) -> bool:
    text = value.casefold()
    markers = (
        "ago",
        "applicant",
        "candidate",
        "promoted",
        "actively",
        "day",
        "week",
        "month",
        "year",
        "день",
        "дня",
        "дней",
        "месяц",
        "кандидат",
        "продвигается",
        "активное",
    )
    return any(marker in text for marker in markers)


def _looks_like_posted_at(value: str) -> bool:
    text = value.casefold()
    markers = (
        "ago",
        "reposted",
        "posted",
        "hour",
        "day",
        "week",
        "month",
        "year",
        "назад",
        "размещ",
        "день",
        "дня",
        "дней",
        "недел",
        "месяц",
        "час",
        "минут",
    )
    return any(marker in text for marker in markers)


def _contains_text(node: Selector, needles: tuple[str, ...]) -> bool:
    text = _node_label(node).casefold()
    return any(needle.casefold() in text for needle in needles)


def _first_matching(values: list[str], needles: tuple[str, ...]) -> str:
    for value in values:
        lowered = value.casefold()
        if any(needle.casefold() in lowered for needle in needles):
            return value
    return ""

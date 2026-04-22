from __future__ import annotations

from typing import Any

from swiss_jobs.core.models import VacancyFull

from .extractors import extract_detail_payload, normalize_linkedin_posted_date


def apply_detail_payload(
    vacancy: VacancyFull,
    payload: dict[str, Any] | None,
    error: str | None = None,
) -> None:
    if payload:
        vacancy.job_posting_schema = payload.get("job_posting_schema")
        vacancy.description_html = str(payload.get("description_html") or "")
        vacancy.description_text = str(payload.get("description_text") or "")
        title = payload.get("title")
        if isinstance(title, str) and title.strip():
            vacancy.title = title.strip()
        company = payload.get("company")
        if isinstance(company, str) and company.strip():
            vacancy.company = company.strip()
        place = payload.get("place")
        if isinstance(place, str) and place.strip():
            vacancy.place = place.strip()

        detail_attributes = payload.get("detail_attributes")
        if isinstance(detail_attributes, dict) and detail_attributes:
            vacancy.raw["detailAttributes"] = detail_attributes
        salary_text = payload.get("salary_text")
        if isinstance(salary_text, str) and salary_text.strip():
            vacancy.raw["salaryText"] = salary_text.strip()
        posted_at_text = payload.get("posted_at_text")
        if isinstance(posted_at_text, str) and posted_at_text.strip():
            clean_posted_at = posted_at_text.strip()
            vacancy.raw["postedAtText"] = clean_posted_at
            normalized_posted_at = normalize_linkedin_posted_date(clean_posted_at)
            if normalized_posted_at:
                vacancy.publication_date = normalized_posted_at
                vacancy.initial_publication_date = vacancy.initial_publication_date or normalized_posted_at

        schema = vacancy.job_posting_schema or {}
        date_posted = schema.get("datePosted")
        if isinstance(date_posted, str) and date_posted.strip():
            vacancy.initial_publication_date = date_posted.strip()
            vacancy.publication_date = vacancy.publication_date or date_posted.strip()
        employment_type = schema.get("employmentType")
        if isinstance(employment_type, list):
            vacancy.raw["employmentType"] = ", ".join(
                str(item).strip() for item in employment_type if str(item).strip()
            )
        elif isinstance(employment_type, str) and employment_type.strip():
            vacancy.raw["employmentType"] = employment_type.strip()
        vacancy.detail_schema_error = None
        return

    vacancy.detail_schema_error = error or "unknown detail fetch error"

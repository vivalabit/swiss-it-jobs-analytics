from __future__ import annotations

from typing import Any

from swiss_jobs.core.models import VacancyFull

from .extractors import extract_detail_payload


def apply_detail_payload(
    vacancy: VacancyFull,
    payload: dict[str, Any] | None,
    error: str | None = None,
) -> None:
    if payload:
        vacancy.job_posting_schema = payload.get("job_posting_schema")
        vacancy.description_html = str(payload.get("description_html") or "")
        vacancy.description_text = str(payload.get("description_text") or "")
        detail_attributes = payload.get("detail_attributes")
        if isinstance(detail_attributes, dict):
            vacancy.raw.update(detail_attributes)
            publication_date = detail_attributes.get("publicationDate")
            if isinstance(publication_date, str) and publication_date.strip():
                if vacancy.publication_date and vacancy.publication_date != publication_date.strip():
                    vacancy.raw.setdefault("publicationDateText", vacancy.publication_date)
                vacancy.publication_date = publication_date.strip()
                vacancy.initial_publication_date = publication_date.strip()
            employment_text = detail_attributes.get("employmentTypeText")
            if isinstance(employment_text, str) and employment_text.strip():
                vacancy.raw["employmentType"] = employment_text.strip()
                vacancy.raw.setdefault("jobType", employment_text.strip())
        vacancy.detail_schema_error = None
        return

    vacancy.detail_schema_error = error or "unknown detail fetch error"

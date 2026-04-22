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
        salary_text = payload.get("salary_text")
        if isinstance(salary_text, str) and salary_text.strip():
            vacancy.raw["salaryText"] = salary_text.strip()

        schema = vacancy.job_posting_schema or {}
        date_posted = schema.get("datePosted")
        if isinstance(date_posted, str) and date_posted.strip():
            vacancy.initial_publication_date = date_posted.strip()
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


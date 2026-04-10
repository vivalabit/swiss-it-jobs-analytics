from __future__ import annotations

from typing import Any

from swiss_jobs.core.models import VacancyFull

from .extractors import extract_job_posting_schema, html_to_text


def extract_detail_payload(page_html: str) -> dict[str, Any]:
    schema = extract_job_posting_schema(page_html)
    description_html = ""
    if isinstance(schema, dict):
        raw_description = schema.get("description")
        if isinstance(raw_description, str):
            description_html = raw_description.strip()

    return {
        "job_posting_schema": schema,
        "description_html": description_html,
        "description_text": html_to_text(description_html) if description_html else "",
    }


def apply_detail_payload(
    vacancy: VacancyFull,
    payload: dict[str, Any] | None,
    error: str | None = None,
) -> None:
    if payload:
        vacancy.job_posting_schema = payload.get("job_posting_schema")
        vacancy.description_html = str(payload.get("description_html") or "")
        vacancy.description_text = str(payload.get("description_text") or "")
        vacancy.detail_schema_error = None
        return

    vacancy.detail_schema_error = error or "unknown detail fetch error"

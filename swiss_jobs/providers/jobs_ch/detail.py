from __future__ import annotations

from typing import Any

from swiss_jobs.core.models import VacancyFull

from .extractors import extract_job_posting_schema, extract_salary_payload, html_to_text


def extract_detail_payload(page_html: str) -> dict[str, Any]:
    schema = extract_job_posting_schema(page_html)
    salary_payload = extract_salary_payload(page_html)
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
                if value:
                    base_salary["value"] = value
                if base_salary.get("currency") and value:
                    schema["baseSalary"] = base_salary

    return {
        "job_posting_schema": schema,
        "description_html": description_html,
        "description_text": html_to_text(description_html) if description_html else "",
        "salary": salary_payload.get("salary") if salary_payload else None,
        "salary_text": salary_payload.get("salary_text") if salary_payload else None,
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
        salary = payload.get("salary")
        if isinstance(salary, dict):
            vacancy.raw["salary"] = salary
        salary_text = payload.get("salary_text")
        if isinstance(salary_text, str) and salary_text.strip():
            vacancy.raw["salaryText"] = salary_text.strip()
        vacancy.detail_schema_error = None
        return

    vacancy.detail_schema_error = error or "unknown detail fetch error"

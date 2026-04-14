from __future__ import annotations

from typing import Any, Sequence

from .models import OutputFormat, VacancyBrief, VacancyFull


def _shorten(text: str, *, limit: int = 280) -> str | None:
    clean = " ".join(text.split())
    if not clean:
        return None
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1].rstrip()}…"


def _extract_salary(vacancy: VacancyFull) -> str | None:
    schema = vacancy.job_posting_schema or {}
    base_salary = schema.get("baseSalary")
    if isinstance(base_salary, dict):
        currency = str(base_salary.get("currency") or "").strip()
        value = base_salary.get("value")
        if isinstance(value, dict):
            min_value = value.get("minValue")
            max_value = value.get("maxValue")
            single_value = value.get("value")
            unit = str(value.get("unitText") or "").strip()
            if min_value is not None and max_value is not None:
                return f"{currency} {min_value}-{max_value} {unit}".strip()
            if single_value is not None:
                return f"{currency} {single_value} {unit}".strip()
        if value is not None:
            return f"{currency} {value}".strip()

    raw = vacancy.raw or {}
    raw_salary = raw.get("salary")
    if isinstance(raw_salary, dict):
        currency = str(raw_salary.get("currency") or "").strip()
        unit = str(raw_salary.get("unit") or "").strip()
        salary_range = raw_salary.get("range")
        if isinstance(salary_range, dict):
            minimum = salary_range.get("minValue")
            maximum = salary_range.get("maxValue")
            unit_suffix = f" / {unit.lower()}" if unit else ""
            currency_prefix = f"{currency} " if currency else ""
            if minimum is not None and maximum is not None:
                if minimum == maximum:
                    return f"{currency_prefix}{int(minimum)}{unit_suffix}".strip()
                return f"{currency_prefix}{int(minimum)}-{int(maximum)}{unit_suffix}".strip()
    for key in ("salary", "salaryText", "salary_text"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_summary(vacancy: VacancyFull) -> str | None:
    for key in ("snippet", "lead", "teaser", "shortDescription", "descriptionPreview"):
        value = vacancy.raw.get(key)
        if isinstance(value, str) and value.strip():
            summary = _shorten(value)
            if summary:
                return summary
    return _shorten(vacancy.description_text)


def build_brief(vacancy: VacancyFull) -> VacancyBrief:
    return VacancyBrief(
        id=vacancy.id,
        title=vacancy.title,
        company=vacancy.company,
        location=vacancy.place,
        posted_at=vacancy.posted_at,
        employment_type=vacancy.employment_type,
        seniority_match=vacancy.seniority_match,
        role_match=vacancy.role_match,
        url=vacancy.url,
        summary=_extract_summary(vacancy),
        salary=_extract_salary(vacancy),
        keywords_matched=list(vacancy.keywords_matched),
        source=vacancy.source,
    )


def format_vacancy(vacancy: VacancyFull, output_format: OutputFormat) -> dict[str, Any]:
    if output_format == "brief":
        return build_brief(vacancy).to_dict()
    return vacancy.to_dict()


def format_vacancies(
    vacancies: Sequence[VacancyFull],
    output_format: OutputFormat,
) -> list[dict[str, Any]]:
    return [format_vacancy(vacancy, output_format) for vacancy in vacancies]

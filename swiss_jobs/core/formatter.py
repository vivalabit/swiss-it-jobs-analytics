from __future__ import annotations

from typing import Any, Sequence

from .models import OutputFormat, VacancyBrief, VacancyFull
from .salary import extract_salary_info


def _shorten(text: str, *, limit: int = 280) -> str | None:
    clean = " ".join(text.split())
    if not clean:
        return None
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1].rstrip()}…"


def _extract_salary(vacancy: VacancyFull) -> str | None:
    return extract_salary_info(vacancy).display_text


def _extract_summary(vacancy: VacancyFull) -> str | None:
    for key in ("snippet", "lead", "teaser", "shortDescription", "descriptionPreview"):
        value = vacancy.raw.get(key)
        if isinstance(value, str) and value.strip():
            summary = _shorten(value)
            if summary:
                return summary
    return _shorten(vacancy.description_text)


def build_brief(vacancy: VacancyFull) -> VacancyBrief:
    salary = extract_salary_info(vacancy)
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
        salary=salary.display_text,
        salary_min=salary.minimum,
        salary_max=salary.maximum,
        salary_currency=salary.currency,
        salary_unit=salary.unit,
        salary_text=salary.text,
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

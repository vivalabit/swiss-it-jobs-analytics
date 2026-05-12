from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .database import JobsDatabase
from .models import VacancyFull
from .salary import SalaryInfo, extract_salary_info, parse_salary_range_text


def hydrate_cached_details(database_path: str | Path, vacancies: Sequence[VacancyFull]) -> int:
    cached = JobsDatabase(database_path).load_cached_vacancy_details(
        vacancy.id for vacancy in vacancies if vacancy.id
    )
    hydrated = 0
    for vacancy in vacancies:
        cached_vacancy = cached.get(vacancy.id)
        if cached_vacancy is None or not has_reusable_detail(cached_vacancy):
            continue
        apply_cached_detail(vacancy, cached_vacancy)
        hydrated += 1
    return hydrated


def has_reusable_detail(vacancy: VacancyFull) -> bool:
    if vacancy.detail_schema_skipped:
        return False
    if vacancy.description_html.strip() or vacancy.description_text.strip():
        return True
    if vacancy.job_posting_schema:
        return True

    salary = extract_salary_info(vacancy)
    return any(
        value is not None and value != ""
        for value in (salary.minimum, salary.maximum, salary.currency, salary.unit, salary.text)
    )


def apply_cached_detail(vacancy: VacancyFull, cached: VacancyFull) -> None:
    merged_raw = dict(cached.raw)
    merged_raw.update(vacancy.raw)
    vacancy.raw = merged_raw

    vacancy.description_html = cached.description_html
    vacancy.description_text = cached.description_text
    vacancy.job_posting_schema = cached.job_posting_schema
    vacancy.detail_schema_error = cached.detail_schema_error
    vacancy.detail_schema_skipped = False
    ensure_salary_from_detail_text(vacancy)


def vacancies_missing_detail(vacancies: Sequence[VacancyFull]) -> list[VacancyFull]:
    return [vacancy for vacancy in vacancies if not has_reusable_detail(vacancy)]


def ensure_salary_from_detail_text(vacancy: VacancyFull) -> None:
    if extract_salary_info(vacancy).display_text:
        return
    salary = parse_salary_range_text(vacancy.description_text)
    if salary is None or salary.minimum is None or salary.maximum is None or salary.currency is None:
        return
    vacancy.raw["salary"] = _salary_info_to_raw(salary)
    if salary.display_text:
        vacancy.raw["salaryText"] = salary.display_text


def _salary_info_to_raw(salary: SalaryInfo) -> dict[str, object]:
    assert salary.minimum is not None
    assert salary.maximum is not None
    assert salary.currency is not None
    payload: dict[str, object] = {
        "currency": salary.currency,
        "range": {
            "minValue": salary.minimum,
            "maxValue": salary.maximum,
        },
    }
    if salary.unit:
        payload["unit"] = salary.unit
    return payload

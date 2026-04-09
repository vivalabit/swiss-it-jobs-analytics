from __future__ import annotations

from typing import Sequence

from .models import FilterDecision, VacancyFull


def split_csv_values(values: Sequence[str] | None) -> list[str]:
    if not values:
        return []

    result: list[str] = []
    for value in values:
        for chunk in str(value).split(","):
            item = chunk.strip()
            if item:
                result.append(item)
    return result


def normalize_tokens(values: Sequence[str] | None) -> list[str]:
    return [item.lower().strip() for item in split_csv_values(values) if item.strip()]


def passes_text_filters(
    vacancy: VacancyFull, include: Sequence[str], exclude: Sequence[str]
) -> bool:
    haystack = " ".join(
        [
            vacancy.title,
            vacancy.company,
            vacancy.place,
        ]
    ).lower()

    if include and not all(token in haystack for token in include):
        return False
    if exclude and any(token in haystack for token in exclude):
        return False
    return True


def make_job_haystack(vacancy: VacancyFull) -> str:
    parts = [
        vacancy.title,
        vacancy.company,
        vacancy.place,
        vacancy.description_text,
        vacancy.description_html,
    ]
    return " ".join(parts).lower()


def evaluate_role_seniority_filters(
    vacancy: VacancyFull,
    role_keywords: Sequence[str],
    seniority_keywords: Sequence[str],
    require_both: bool,
) -> FilterDecision:
    normalized_roles = [token for token in role_keywords if token]
    normalized_seniority = [token for token in seniority_keywords if token]
    if not normalized_roles and not normalized_seniority:
        return FilterDecision(passes=True)

    haystack = make_job_haystack(vacancy)
    matched_keywords: list[str] = []

    role_match: bool | None = None
    if normalized_roles:
        matched_role = [token for token in normalized_roles if token in haystack]
        role_match = bool(matched_role)
        matched_keywords.extend(matched_role)

    seniority_match: bool | None = None
    if normalized_seniority:
        matched_seniority = [token for token in normalized_seniority if token in haystack]
        seniority_match = bool(matched_seniority)
        matched_keywords.extend(matched_seniority)

    if normalized_roles and normalized_seniority:
        passes = (
            bool(role_match) and bool(seniority_match)
            if require_both
            else bool(role_match) or bool(seniority_match)
        )
    else:
        passes = bool(role_match) if role_match is not None else bool(seniority_match)

    deduped_keywords: list[str] = []
    seen: set[str] = set()
    for keyword in matched_keywords:
        if keyword not in seen:
            seen.add(keyword)
            deduped_keywords.append(keyword)

    return FilterDecision(
        passes=passes,
        role_match=role_match,
        seniority_match=seniority_match,
        matched_keywords=deduped_keywords,
    )


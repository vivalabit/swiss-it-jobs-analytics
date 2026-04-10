from __future__ import annotations

from typing import Sequence

from .models import VacancyFull

def compute_new_ids(
    vacancies: Sequence[VacancyFull],
    seen_ids: Sequence[str],
    *,
    bootstrap: bool,
) -> tuple[set[str], list[str]]:
    seen_list = [str(item) for item in seen_ids if str(item)]
    seen_set = set(seen_list)

    if bootstrap:
        for vacancy in vacancies:
            if vacancy.id and vacancy.id not in seen_set:
                seen_set.add(vacancy.id)
                seen_list.append(vacancy.id)
        return set(), seen_list

    new_ids = {
        vacancy.id
        for vacancy in vacancies
        if vacancy.id and vacancy.id not in seen_set
    }
    for vacancy in vacancies:
        if vacancy.id and vacancy.id not in seen_set:
            seen_set.add(vacancy.id)
            seen_list.append(vacancy.id)
    return new_ids, seen_list

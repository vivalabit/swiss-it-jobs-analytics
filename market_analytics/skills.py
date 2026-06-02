from __future__ import annotations

from collections import Counter
from itertools import combinations

import pandas as pd

from swiss_jobs.core.skill_taxonomy import SKILL_CATEGORIES, category_for_skill

from .constants import UNKNOWN_LABEL


def calculate_top_skills_overall(
    dataset: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    exploded = _explode_list_column(
        dataset=dataset,
        list_column="skills_list",
        item_column_name="skill",
    )
    if exploded.empty:
        return pd.DataFrame(columns=["skill", "vacancy_count", "share"])

    counts = (
        exploded["skill"]
        .value_counts()
        .rename_axis("skill")
        .reset_index(name="vacancy_count")
        .head(top_n)
    )
    counts["share"] = (counts["vacancy_count"] / len(dataset)).round(4)
    return counts


def calculate_top_skills_by_dimension(
    dataset: pd.DataFrame,
    dimension: str,
    top_n: int = 20,
) -> pd.DataFrame:
    exploded = _explode_list_column(
        dataset=dataset,
        list_column="skills_list",
        item_column_name="skill",
        dimension=dimension,
    )
    if exploded.empty:
        return pd.DataFrame(
            columns=[dimension, "skill", "vacancy_count", "share_within_group", "rank"]
        )

    grouped = (
        exploded.groupby([dimension, "skill"])
        .size()
        .reset_index(name="vacancy_count")
        .sort_values([dimension, "vacancy_count", "skill"], ascending=[True, False, True])
    )
    grouped["rank"] = (
        grouped.groupby(dimension)["vacancy_count"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )

    group_totals = (
        dataset[dimension]
        .fillna(UNKNOWN_LABEL)
        .value_counts(dropna=False)
        .rename_axis(dimension)
        .reset_index(name="group_vacancy_count")
    )
    grouped = grouped.merge(group_totals, on=dimension, how="left")
    grouped["share_within_group"] = (
        grouped["vacancy_count"] / grouped["group_vacancy_count"]
    ).round(4)
    grouped = grouped[grouped["rank"] <= top_n]
    return grouped.drop(columns=["group_vacancy_count"]).reset_index(drop=True)


def calculate_skill_cooccurrence_pairs(
    dataset: pd.DataFrame,
    top_n: int = 50,
) -> pd.DataFrame:
    pair_counter: Counter[tuple[str, str]] = Counter()
    for skills in dataset["skills_list"]:
        unique_skills = sorted(set(skills))
        for pair in combinations(unique_skills, 2):
            pair_counter[pair] += 1

    rows = [
        {"skill_1": left, "skill_2": right, "vacancy_count": count}
        for (left, right), count in pair_counter.most_common(top_n)
    ]
    return pd.DataFrame(rows, columns=["skill_1", "skill_2", "vacancy_count"])


def calculate_top_list_items(
    dataset: pd.DataFrame,
    list_column: str,
    item_label: str,
    top_n: int = 20,
) -> pd.DataFrame:
    exploded = _explode_list_column(
        dataset=dataset,
        list_column=list_column,
        item_column_name=item_label,
    )
    if exploded.empty:
        return pd.DataFrame(columns=[item_label, "vacancy_count", "share"])

    counts = (
        exploded[item_label]
        .value_counts()
        .rename_axis(item_label)
        .reset_index(name="vacancy_count")
        .head(top_n)
    )
    counts["share"] = (counts["vacancy_count"] / len(dataset)).round(4)
    return counts


def calculate_list_summary(
    dataset: pd.DataFrame,
    list_column: str,
) -> pd.DataFrame:
    if list_column not in dataset.columns:
        return _build_summary_frame(
            distinct_items=0,
            total_mentions=0,
            vacancies_with_items=0,
            vacancy_coverage=0.0,
        )

    values = dataset[list_column]
    distinct_items = len({item for items in values for item in items})
    total_mentions = int(sum(len(items) for items in values))
    vacancies_with_items = int(sum(1 for items in values if items))
    vacancy_coverage = round(vacancies_with_items / len(dataset), 4) if len(dataset) else 0.0
    return _build_summary_frame(
        distinct_items=distinct_items,
        total_mentions=total_mentions,
        vacancies_with_items=vacancies_with_items,
        vacancy_coverage=vacancy_coverage,
    )


def calculate_top_skills_by_category(
    dataset: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    rows = _taxonomy_rows(dataset)
    columns = ["category", "skill", "vacancy_count", "share", "rank"]
    if not rows:
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame.from_records(rows).drop_duplicates(
        subset=["vacancy_index", "category", "skill"]
    )
    grouped = (
        frame.groupby(["category", "skill"])
        .size()
        .reset_index(name="vacancy_count")
        .sort_values(["category", "vacancy_count", "skill"], ascending=[True, False, True])
    )
    grouped["share"] = (grouped["vacancy_count"] / len(dataset)).round(4)
    grouped["rank"] = (
        grouped.groupby("category")["vacancy_count"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )
    grouped = grouped[grouped["rank"] <= top_n]
    return grouped[columns].reset_index(drop=True)


def calculate_skill_taxonomy_summary(dataset: pd.DataFrame) -> pd.DataFrame:
    rows = _taxonomy_rows(dataset)
    columns = [
        "category",
        "distinct_items",
        "total_mentions",
        "vacancies_with_items",
        "vacancy_coverage",
    ]
    if not rows:
        return pd.DataFrame(
            [
                {
                    "category": category,
                    "distinct_items": 0,
                    "total_mentions": 0,
                    "vacancies_with_items": 0,
                    "vacancy_coverage": 0.0,
                }
                for category in SKILL_CATEGORIES
            ],
            columns=columns,
        )

    frame = pd.DataFrame.from_records(rows).drop_duplicates(
        subset=["vacancy_index", "category", "skill"]
    )
    summary_rows: list[dict[str, int | float | str]] = []
    for category in SKILL_CATEGORIES:
        category_frame = frame[frame["category"] == category]
        vacancies_with_items = int(category_frame["vacancy_index"].nunique())
        summary_rows.append(
            {
                "category": category,
                "distinct_items": int(category_frame["skill"].nunique()),
                "total_mentions": int(len(category_frame)),
                "vacancies_with_items": vacancies_with_items,
                "vacancy_coverage": (
                    round(vacancies_with_items / len(dataset), 4) if len(dataset) else 0.0
                ),
            }
        )
    return pd.DataFrame(summary_rows, columns=columns)


def _build_summary_frame(
    *,
    distinct_items: int,
    total_mentions: int,
    vacancies_with_items: int,
    vacancy_coverage: float,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric": "distinct_items", "value": distinct_items},
            {"metric": "total_mentions", "value": total_mentions},
            {"metric": "vacancies_with_items", "value": vacancies_with_items},
            {"metric": "vacancy_coverage", "value": vacancy_coverage},
        ]
    )


def _taxonomy_rows(dataset: pd.DataFrame) -> list[dict[str, int | str]]:
    if "skills_list" not in dataset.columns:
        return []

    rows: list[dict[str, int | str]] = []
    for vacancy_index, skills in enumerate(dataset["skills_list"]):
        if not isinstance(skills, list):
            continue
        for skill in skills:
            category = category_for_skill(skill)
            if category is None:
                continue
            rows.append(
                {
                    "vacancy_index": vacancy_index,
                    "category": category,
                    "skill": str(skill),
                }
            )
    return rows


def _explode_list_column(
    dataset: pd.DataFrame,
    list_column: str,
    item_column_name: str,
    dimension: str | None = None,
) -> pd.DataFrame:
    columns = [list_column]
    if dimension is not None:
        columns.insert(0, dimension)

    exploded = dataset[columns].explode(list_column).rename(columns={list_column: item_column_name})
    exploded = exploded.dropna(subset=[item_column_name]).copy()
    if exploded.empty:
        return exploded

    exploded[item_column_name] = exploded[item_column_name].astype(str)
    if dimension is not None:
        exploded[dimension] = exploded[dimension].fillna(UNKNOWN_LABEL)
    return exploded

from __future__ import annotations

from collections import Counter
from itertools import combinations

import pandas as pd

from .constants import UNKNOWN_LABEL


def calculate_top_skills_overall(
    dataset: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    exploded = _explode_skills(dataset)
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
    exploded = _explode_skills(dataset, dimension=dimension)
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


def _explode_skills(
    dataset: pd.DataFrame,
    dimension: str | None = None,
) -> pd.DataFrame:
    columns = ["skills_list"]
    if dimension is not None:
        columns.insert(0, dimension)

    exploded = dataset[columns].explode("skills_list").rename(columns={"skills_list": "skill"})
    exploded = exploded.dropna(subset=["skill"]).copy()
    if exploded.empty:
        return exploded

    exploded["skill"] = exploded["skill"].astype(str)
    if dimension is not None:
        exploded[dimension] = exploded[dimension].fillna(UNKNOWN_LABEL)
    return exploded

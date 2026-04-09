from __future__ import annotations

import pandas as pd

from .constants import DISTRIBUTION_COLUMNS, UNKNOWN_LABEL


def calculate_overview_metrics(dataset: pd.DataFrame) -> pd.DataFrame:
    total_vacancies = int(len(dataset))
    total_companies = int(dataset["company"].dropna().nunique())
    average_vacancies_per_company = (
        total_vacancies / total_companies if total_companies else 0.0
    )

    return pd.DataFrame(
        [
            {"metric": "total_vacancies", "value": total_vacancies},
            {"metric": "total_companies", "value": total_companies},
            {
                "metric": "average_vacancies_per_company",
                "value": round(average_vacancies_per_company, 2),
            },
        ]
    )


def calculate_distribution(dataset: pd.DataFrame, column: str) -> pd.DataFrame:
    counts = (
        dataset[column]
        .fillna(UNKNOWN_LABEL)
        .value_counts(dropna=False)
        .rename_axis(column)
        .reset_index(name="vacancy_count")
    )
    counts["share"] = (counts["vacancy_count"] / len(dataset)).round(4)
    return counts.sort_values(["vacancy_count", column], ascending=[False, True]).reset_index(
        drop=True
    )


def calculate_distributions(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        f"distribution_{column}": calculate_distribution(dataset, column)
        for column in DISTRIBUTION_COLUMNS
    }


def calculate_crosstab(
    dataset: pd.DataFrame,
    index_column: str,
    columns_column: str,
) -> pd.DataFrame:
    crosstab = pd.crosstab(
        dataset[index_column].fillna(UNKNOWN_LABEL),
        dataset[columns_column].fillna(UNKNOWN_LABEL),
    )
    crosstab.index.name = index_column
    return crosstab.reset_index()


def calculate_crosstabs(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "crosstab_role_category_vs_seniority": calculate_crosstab(
            dataset=dataset,
            index_column="role_category",
            columns_column="seniority",
        ),
        "crosstab_role_category_vs_work_mode": calculate_crosstab(
            dataset=dataset,
            index_column="role_category",
            columns_column="work_mode",
        ),
    }

from __future__ import annotations

import pandas as pd

from .constants import DISTRIBUTION_COLUMNS, UNKNOWN_LABEL

MIN_ANNUAL_SALARY = 20_000
MAX_ANNUAL_SALARY = 300_000


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


def calculate_salary_summary(dataset: pd.DataFrame) -> pd.DataFrame:
    salaries = _annual_salary_frame(dataset)
    salary_count = int(len(salaries))
    salary_coverage = salary_count / len(dataset) if len(dataset) else 0.0

    metrics: list[dict[str, float | int | str]] = [
        {"metric": "salary_count", "value": salary_count},
        {"metric": "salary_coverage", "value": round(salary_coverage, 4)},
    ]
    if salary_count:
        annual_salary = salaries["annual_salary"]
        metrics.extend(
            [
                {"metric": "average_salary", "value": round(float(annual_salary.mean()), 0)},
                {"metric": "median_salary", "value": round(float(annual_salary.median()), 0)},
                {"metric": "p25_salary", "value": round(float(annual_salary.quantile(0.25)), 0)},
                {"metric": "p75_salary", "value": round(float(annual_salary.quantile(0.75)), 0)},
                {"metric": "min_salary", "value": round(float(annual_salary.min()), 0)},
                {"metric": "max_salary", "value": round(float(annual_salary.max()), 0)},
                {"metric": "currency", "value": "CHF"},
                {"metric": "unit", "value": "YEAR"},
            ]
        )
    return pd.DataFrame(metrics)


def calculate_salary_by_role_category(dataset: pd.DataFrame) -> pd.DataFrame:
    salaries = _annual_salary_frame(dataset)
    if salaries.empty:
        return pd.DataFrame(
            columns=[
                "role_category",
                "salary_count",
                "average_salary",
                "median_salary",
                "min_salary",
                "max_salary",
                "rank",
            ]
        )

    grouped = (
        salaries.groupby("role_category", dropna=False)["annual_salary"]
        .agg(
            salary_count="count",
            average_salary="mean",
            median_salary="median",
            min_salary="min",
            max_salary="max",
        )
        .reset_index()
    )
    grouped["role_category"] = grouped["role_category"].fillna(UNKNOWN_LABEL)
    for column in ("average_salary", "median_salary", "min_salary", "max_salary"):
        grouped[column] = grouped[column].round(0).astype(int)
    grouped = grouped.sort_values(
        ["average_salary", "salary_count", "role_category"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    grouped["rank"] = grouped.index + 1
    return grouped


def _annual_salary_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    required_columns = {"salary_min", "salary_max", "salary_currency", "salary_unit"}
    if not required_columns.issubset(dataset.columns):
        return pd.DataFrame(columns=["role_category", "annual_salary"])

    minimum = pd.to_numeric(dataset["salary_min"], errors="coerce")
    maximum = pd.to_numeric(dataset["salary_max"], errors="coerce")
    lower = minimum.fillna(maximum)
    upper = maximum.fillna(minimum)
    midpoint = (lower + upper) / 2.0

    currency = dataset["salary_currency"].astype("string").str.upper()
    unit = dataset["salary_unit"].astype("string").str.upper()
    annual_salary = midpoint.copy()
    annual_salary = annual_salary.where(unit != "MONTH", annual_salary * 12)

    comparable_mask = (
        currency.eq("CHF")
        & unit.isin(["YEAR", "MONTH"])
        & annual_salary.notna()
        & annual_salary.between(MIN_ANNUAL_SALARY, MAX_ANNUAL_SALARY)
    )

    salaries = pd.DataFrame(
        {
            "role_category": dataset["role_category"].fillna(UNKNOWN_LABEL),
            "annual_salary": annual_salary,
        }
    )
    return salaries.loc[comparable_mask].reset_index(drop=True)

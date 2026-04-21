from __future__ import annotations

import re
import unicodedata

import pandas as pd

from .constants import DISTRIBUTION_COLUMNS, STAFFING_AGENCY_COMPANY_NAMES, UNKNOWN_LABEL

MIN_ANNUAL_SALARY = 20_000
MAX_ANNUAL_SALARY = 300_000
HIGHER_EDUCATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        r"\b(?:bachelor|master|msc|bsc|phd|doctorate)\b",
        r"\b(?:university|college)\s+degree\b",
        r"\bdegree\s+in\s+(?:computer science|informatics|engineering|mathematics|physics|it)\b",
        r"\b(?:computer science|informatics|engineering|mathematics|physics)\s+degree\b",
        r"\b(?:eth|epfl|fh|tu)\b",
        r"\bhochschulabschluss\b",
        r"\bhochschulstudium\b",
        r"\b(?:fachhochschule|universitat|universitaet|hochschule)\b",
        r"\b(?:informatikstudium|wirtschaftsinformatikstudium)\b",
        r"\b(?:abschluss|studium)\s+(?:in|der|im)\s+(?:informatik|wirtschaftsinformatik|ingenieurwesen|mathematik|physik)\b",
        r"\b(?:diplom|diploma)\s+(?:in|der|im)?\s*(?:informatik|wirtschaftsinformatik|engineering|computer science)\b",
        r"\b(?:formation|diplome)\s+(?:universitaire|superieure)\b",
    )
)


def calculate_overview_metrics(dataset: pd.DataFrame) -> pd.DataFrame:
    total_vacancies = int(len(dataset))
    direct_employer_dataset = _exclude_staffing_agencies(dataset)
    total_companies = int(direct_employer_dataset["company"].dropna().nunique())
    average_vacancies_per_company = (
        len(direct_employer_dataset) / total_companies if total_companies else 0.0
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


def calculate_education_requirements_summary(dataset: pd.DataFrame) -> pd.DataFrame:
    total_vacancies = int(len(dataset))
    if total_vacancies == 0:
        higher_education_count = 0
    else:
        higher_education_count = int(
            dataset.apply(_has_higher_education_requirement, axis=1).sum()
        )
    share = higher_education_count / total_vacancies if total_vacancies else 0.0

    return pd.DataFrame(
        [
            {"metric": "total_vacancies", "value": total_vacancies},
            {
                "metric": "higher_education_vacancy_count",
                "value": higher_education_count,
            },
            {
                "metric": "higher_education_vacancy_share",
                "value": round(share, 4),
            },
            {
                "metric": "without_explicit_higher_education_count",
                "value": total_vacancies - higher_education_count,
            },
        ]
    )


def _has_higher_education_requirement(row: pd.Series) -> bool:
    text = " ".join(
        str(value)
        for value in (
            row.get("title"),
            row.get("description_text"),
            row.get("salary_text"),
        )
        if not pd.isna(value) and str(value).strip()
    )
    if not text:
        return False

    normalized = _normalize_search_text(text)
    return any(pattern.search(normalized) for pattern in HIGHER_EDUCATION_PATTERNS)


def _normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    without_marks = "".join(
        character for character in normalized if unicodedata.category(character) != "Mn"
    )
    return without_marks.casefold()


def _exclude_staffing_agencies(dataset: pd.DataFrame) -> pd.DataFrame:
    company_names = dataset["company"].map(_normalize_company_name)
    return dataset.loc[~company_names.isin(NORMALIZED_STAFFING_AGENCY_COMPANY_NAMES)]


def _normalize_company_name(value: object) -> str:
    if pd.isna(value):
        return ""
    normalized = unicodedata.normalize("NFD", str(value))
    without_marks = "".join(
        character for character in normalized if unicodedata.category(character) != "Mn"
    )
    without_marks = without_marks.replace("&", " and ")
    without_marks = without_marks.replace("®", "").replace("™", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", without_marks)).strip().casefold()


NORMALIZED_STAFFING_AGENCY_COMPANY_NAMES = frozenset(
    _normalize_company_name(company) for company in STAFFING_AGENCY_COMPANY_NAMES
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
    return calculate_salary_by_dimension(dataset, "role_category")


def calculate_salary_by_seniority(dataset: pd.DataFrame) -> pd.DataFrame:
    return calculate_salary_by_dimension(dataset, "seniority")


def calculate_salary_by_dimension(dataset: pd.DataFrame, dimension: str) -> pd.DataFrame:
    salaries = _annual_salary_frame(dataset)
    if salaries.empty:
        return pd.DataFrame(
            columns=[
                dimension,
                "salary_count",
                "average_salary",
                "median_salary",
                "min_salary",
                "max_salary",
                "rank",
            ]
        )

    grouped = (
        salaries.groupby(dimension, dropna=False)["annual_salary"]
        .agg(
            salary_count="count",
            average_salary="mean",
            median_salary="median",
            min_salary="min",
            max_salary="max",
        )
        .reset_index()
    )
    grouped[dimension] = grouped[dimension].fillna(UNKNOWN_LABEL)
    for column in ("average_salary", "median_salary", "min_salary", "max_salary"):
        grouped[column] = grouped[column].round(0).astype(int)
    grouped = grouped.sort_values(
        ["average_salary", "salary_count", dimension],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    grouped["rank"] = grouped.index + 1
    return grouped


def _annual_salary_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    required_columns = {"salary_min", "salary_max", "salary_currency", "salary_unit"}
    if not required_columns.issubset(dataset.columns):
        return pd.DataFrame(columns=["role_category", "seniority", "annual_salary"])

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
            "seniority": dataset["seniority"].fillna(UNKNOWN_LABEL),
            "annual_salary": annual_salary,
        }
    )
    return salaries.loc[comparable_mask].reset_index(drop=True)

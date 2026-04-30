from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Mapping

import pandas as pd

from .analytics import (
    _parse_datetime_series,
    exclude_staffing_agencies,
    calculate_education_requirements_summary,
    calculate_experience_by_seniority,
    calculate_experience_requirements_summary,
    calculate_crosstabs,
    calculate_city_map_details,
    calculate_distributions,
    calculate_overview_metrics,
    calculate_salary_by_role_category,
    calculate_salary_by_seniority,
    calculate_salary_summary,
    calculate_vacancy_trend_outputs,
)
from .constants import PUBLIC_ANALYTICS_MIN_PUBLICATION_DATE
from .deduplication import deduplicate_cross_source_vacancies
from .skills import (
    calculate_list_summary,
    calculate_skill_cooccurrence_pairs,
    calculate_top_list_items,
    calculate_top_skills_by_dimension,
    calculate_top_skills_overall,
)

PUBLIC_ANALYTICS_MIN_PUBLICATION_TIMESTAMP = pd.Timestamp(
    PUBLIC_ANALYTICS_MIN_PUBLICATION_DATE,
    tz=UTC,
)


def build_analytics_outputs(
    dataset: pd.DataFrame,
    top_skills_limit: int = 20,
    top_skill_pairs_limit: int = 50,
) -> dict[str, pd.DataFrame]:
    dataset = deduplicate_cross_source_vacancies(dataset).reset_index(drop=True)
    dataset = exclude_staffing_agencies(dataset).reset_index(drop=True)
    dataset = _filter_dataset_to_public_coverage(dataset).reset_index(drop=True)
    outputs: dict[str, pd.DataFrame] = {
        "overview_metrics": calculate_overview_metrics(dataset),
        "education_requirements_summary": calculate_education_requirements_summary(dataset),
        "experience_requirements_summary": calculate_experience_requirements_summary(dataset),
        "experience_by_seniority": calculate_experience_by_seniority(dataset),
        "salary_summary": calculate_salary_summary(dataset),
        "salary_by_role_category": calculate_salary_by_role_category(dataset),
        "salary_by_seniority": calculate_salary_by_seniority(dataset),
        **calculate_distributions(dataset),
        "city_map_details": calculate_city_map_details(dataset),
        "top_skills_overall": calculate_top_skills_overall(
            dataset,
            top_n=top_skills_limit,
        ),
        "top_skills_by_role_category": calculate_top_skills_by_dimension(
            dataset,
            dimension="role_category",
            top_n=top_skills_limit,
        ),
        "top_skills_by_canton": calculate_top_skills_by_dimension(
            dataset,
            dimension="canton",
            top_n=top_skills_limit,
        ),
        "top_programming_languages": calculate_top_list_items(
            dataset,
            list_column="programming_languages_list",
            item_label="programming_language",
            top_n=top_skills_limit,
        ),
        "programming_languages_summary": calculate_list_summary(
            dataset,
            list_column="programming_languages_list",
        ),
        "top_frameworks_libraries": calculate_top_list_items(
            dataset,
            list_column="frameworks_libraries_list",
            item_label="framework_library",
            top_n=top_skills_limit,
        ),
        "frameworks_libraries_summary": calculate_list_summary(
            dataset,
            list_column="frameworks_libraries_list",
        ),
        "skill_cooccurrence_pairs": calculate_skill_cooccurrence_pairs(
            dataset,
            top_n=top_skill_pairs_limit,
        ),
        **calculate_vacancy_trend_outputs(dataset),
        **calculate_crosstabs(dataset),
    }
    return outputs


def _filter_dataset_to_public_coverage(dataset: pd.DataFrame) -> pd.DataFrame:
    if "publication_date" not in dataset.columns:
        return dataset.iloc[0:0].copy()

    published_at = _parse_datetime_series(dataset["publication_date"])
    coverage_mask = published_at >= PUBLIC_ANALYTICS_MIN_PUBLICATION_TIMESTAMP
    return dataset.loc[coverage_mask.fillna(False)].copy()


def save_analytics_outputs(
    outputs: Mapping[str, pd.DataFrame],
    output_directory: str | Path,
) -> list[Path]:
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    for output_name, frame in outputs.items():
        target_path = output_path / f"{output_name}.csv"
        frame.to_csv(target_path, index=False)
        saved_paths.append(target_path)
    return saved_paths

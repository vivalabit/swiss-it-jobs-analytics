from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from .analytics import (
    calculate_crosstabs,
    calculate_distributions,
    calculate_overview_metrics,
)
from .skills import (
    calculate_list_summary,
    calculate_skill_cooccurrence_pairs,
    calculate_top_list_items,
    calculate_top_skills_by_dimension,
    calculate_top_skills_overall,
)


def build_analytics_outputs(
    dataset: pd.DataFrame,
    top_skills_limit: int = 20,
    top_skill_pairs_limit: int = 50,
) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {
        "overview_metrics": calculate_overview_metrics(dataset),
        **calculate_distributions(dataset),
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
        **calculate_crosstabs(dataset),
    }
    return outputs


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

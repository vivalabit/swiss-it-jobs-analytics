from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

EXPECTED_CSV_FILES: tuple[str, ...] = (
    "overview_metrics.csv",
    "city_map_details.csv",
    "education_requirements_summary.csv",
    "experience_requirements_summary.csv",
    "experience_by_seniority.csv",
    "salary_summary.csv",
    "salary_by_role_category.csv",
    "salary_by_seniority.csv",
    "top_skills_overall.csv",
    "top_skills_by_role_category.csv",
    "top_skills_by_canton.csv",
    "top_programming_languages.csv",
    "programming_languages_summary.csv",
    "top_frameworks_libraries.csv",
    "frameworks_libraries_summary.csv",
    "vacancy_trends_summary.csv",
    "vacancy_trends_daily.csv",
    "vacancy_trends_weekly.csv",
    "vacancy_trends_monthly.csv",
    "vacancy_trends_segments_daily.csv",
    "vacancy_trends_segments_weekly.csv",
    "distribution_role_category.csv",
    "distribution_company.csv",
    "distribution_city.csv",
    "distribution_canton.csv",
    "distribution_seniority.csv",
    "distribution_work_mode.csv",
    "skill_cooccurrence_pairs.csv",
)

DISTRIBUTION_DIMENSIONS: tuple[str, ...] = (
    "company",
    "role_category",
    "city",
    "canton",
    "seniority",
    "work_mode",
)


def build_public_snapshots(
    *,
    csv_dir: Path,
    output_dir: Path,
    copy_csv_dir: Path | None = None,
) -> list[Path]:
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    csv_frames = _load_csv_frames(csv_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_generated_files(output_dir, "*.json")

    if copy_csv_dir is not None:
        copy_csv_dir.mkdir(parents=True, exist_ok=True)
        _clear_generated_files(copy_csv_dir, "*.csv")
        for file_name, frame in csv_frames.items():
            if frame is None:
                continue
            frame.to_csv(copy_csv_dir / file_name, index=False)

    snapshots: dict[str, dict[str, Any]] = {
        "metadata.json": _build_metadata_snapshot(
            generated_at=generated_at,
            csv_dir=csv_dir,
            output_dir=output_dir,
            csv_frames=csv_frames,
        ),
        "overview.json": _build_overview_snapshot(
            generated_at=generated_at,
            overview_frame=csv_frames["overview_metrics.csv"],
        ),
        "city_map_details.json": _build_city_map_details_snapshot(
            generated_at=generated_at,
            frame=csv_frames["city_map_details.csv"],
        ),
        "education_requirements.json": _build_education_requirements_snapshot(
            generated_at=generated_at,
            summary_frame=csv_frames["education_requirements_summary.csv"],
        ),
        "experience_requirements.json": _build_experience_requirements_snapshot(
            generated_at=generated_at,
            summary_frame=csv_frames["experience_requirements_summary.csv"],
            by_seniority_frame=csv_frames["experience_by_seniority.csv"],
        ),
        "salary_metrics.json": _build_salary_snapshot(
            generated_at=generated_at,
            summary_frame=csv_frames["salary_summary.csv"],
            by_role_category_frame=csv_frames["salary_by_role_category.csv"],
            by_seniority_frame=csv_frames["salary_by_seniority.csv"],
        ),
        "top_skills.json": _build_top_skills_snapshot(
            generated_at=generated_at,
            overall_frame=csv_frames["top_skills_overall.csv"],
            by_role_category_frame=csv_frames["top_skills_by_role_category.csv"],
            by_canton_frame=csv_frames["top_skills_by_canton.csv"],
            programming_languages_frame=csv_frames["top_programming_languages.csv"],
            programming_languages_summary_frame=csv_frames["programming_languages_summary.csv"],
            frameworks_frame=csv_frames["top_frameworks_libraries.csv"],
            frameworks_summary_frame=csv_frames["frameworks_libraries_summary.csv"],
        ),
        "skill_pairs.json": _build_items_snapshot(
            generated_at=generated_at,
            frame=csv_frames["skill_cooccurrence_pairs.csv"],
            items_key="items",
        ),
        "vacancy_trends.json": _build_vacancy_trends_snapshot(
            generated_at=generated_at,
            summary_frame=csv_frames["vacancy_trends_summary.csv"],
            daily_frame=csv_frames["vacancy_trends_daily.csv"],
            weekly_frame=csv_frames["vacancy_trends_weekly.csv"],
            monthly_frame=csv_frames["vacancy_trends_monthly.csv"],
            daily_segments_frame=csv_frames["vacancy_trends_segments_daily.csv"],
            weekly_segments_frame=csv_frames["vacancy_trends_segments_weekly.csv"],
        ),
    }

    for dimension in DISTRIBUTION_DIMENSIONS:
        file_name = f"distribution_{dimension}.csv"
        snapshots[f"distributions_{dimension}.json"] = _build_distribution_snapshot(
            generated_at=generated_at,
            dimension=dimension,
            frame=csv_frames[file_name],
        )

    saved_paths: list[Path] = []
    for file_name, payload in snapshots.items():
        path = output_dir / file_name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        saved_paths.append(path)
    return saved_paths


def _load_csv_frames(csv_dir: Path) -> dict[str, pd.DataFrame | None]:
    frames: dict[str, pd.DataFrame | None] = {}
    for file_name in EXPECTED_CSV_FILES:
        path = csv_dir / file_name
        frames[file_name] = pd.read_csv(path) if path.exists() else None
    frames["city_map_details.csv"] = _reconcile_city_map_details_frame(
        frames.get("city_map_details.csv"),
        frames.get("distribution_city.csv"),
    )
    return frames


def _reconcile_city_map_details_frame(
    details_frame: pd.DataFrame | None,
    distribution_city_frame: pd.DataFrame | None,
) -> pd.DataFrame | None:
    if distribution_city_frame is None or not {"city", "vacancy_count", "share"}.issubset(
        distribution_city_frame.columns
    ):
        return details_frame
    if details_frame is None or "city" not in details_frame.columns:
        return details_frame

    details_by_city = {
        str(row["city"]): row for row in details_frame.to_dict(orient="records") if row.get("city") is not None
    }
    reconciled_rows: list[dict[str, Any]] = []

    for row in distribution_city_frame.to_dict(orient="records"):
        city = _to_python_value(row.get("city"))
        vacancy_count = _to_python_value(row.get("vacancy_count"))
        share = _to_python_value(row.get("share"))
        detail_row = details_by_city.get(str(city))
        source_total = detail_row.get("vacancy_count") if detail_row else None
        reconciled_rows.append(
            {
                "city": city,
                "vacancy_count": vacancy_count,
                "share": share,
                "role_distribution_json": _rescale_distribution_json(
                    detail_row.get("role_distribution_json") if detail_row else None,
                    source_total=source_total,
                    target_total=vacancy_count,
                ),
                "company_distribution_json": _rescale_distribution_json(
                    detail_row.get("company_distribution_json") if detail_row else None,
                    source_total=source_total,
                    target_total=vacancy_count,
                ),
                "work_mode_distribution_json": _rescale_distribution_json(
                    detail_row.get("work_mode_distribution_json") if detail_row else None,
                    source_total=source_total,
                    target_total=vacancy_count,
                ),
            }
        )

    return pd.DataFrame.from_records(reconciled_rows)


def _rescale_distribution_json(
    value: Any,
    *,
    source_total: Any,
    target_total: Any,
) -> str:
    items = _parse_json_array_value(value)
    target_total_value = _coerce_numeric(target_total)
    source_total_value = _coerce_numeric(source_total)
    if not items or target_total_value is None or target_total_value <= 0:
        return "[]"

    normalized_items: list[dict[str, Any]] = []
    for item in items:
        count = _coerce_numeric(item.get("vacancy_count"))
        if count is None or count <= 0:
            continue
        normalized_items.append(dict(item))
    if not normalized_items:
        return "[]"

    if source_total_value is None or source_total_value <= 0:
        source_total_value = sum(_coerce_numeric(item.get("vacancy_count")) or 0 for item in normalized_items)
    scale = target_total_value / source_total_value if source_total_value else 0

    scaled_items: list[dict[str, Any]] = []
    for item in normalized_items:
        scaled_item = dict(item)
        vacancy_count = (_coerce_numeric(item.get("vacancy_count")) or 0) * scale
        scaled_item["vacancy_count"] = round(vacancy_count, 4)
        scaled_item["share_within_city"] = (
            round(vacancy_count / target_total_value, 4) if target_total_value else 0
        )
        scaled_items.append(scaled_item)
    return json.dumps(scaled_items, ensure_ascii=False)


def _build_metadata_snapshot(
    *,
    generated_at: str,
    csv_dir: Path,
    output_dir: Path,
    csv_frames: dict[str, pd.DataFrame | None],
) -> dict[str, Any]:
    available_csv_files = [file_name for file_name, frame in csv_frames.items() if frame is not None]
    missing_csv_files = [file_name for file_name, frame in csv_frames.items() if frame is None]
    generated_snapshots = [
        "metadata.json",
        "overview.json",
        "city_map_details.json",
        "education_requirements.json",
        "experience_requirements.json",
        "salary_metrics.json",
        "top_skills.json",
        "skill_pairs.json",
        "vacancy_trends.json",
        *[f"distributions_{dimension}.json" for dimension in DISTRIBUTION_DIMENSIONS],
    ]
    return {
        "generated_at": generated_at,
        "schema_version": 3,
        "source_csv_dir": str(csv_dir),
        "public_data_dir": str(output_dir),
        "available_csv_files": available_csv_files,
        "missing_csv_files": missing_csv_files,
        "generated_snapshots": generated_snapshots,
    }


def _build_overview_snapshot(
    *,
    generated_at: str,
    overview_frame: pd.DataFrame | None,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if overview_frame is not None and {"metric", "value"}.issubset(overview_frame.columns):
        metrics = {
            str(row["metric"]): _normalize_metric_value(str(row["metric"]), row["value"])
            for row in overview_frame.to_dict(orient="records")
        }
    return {
        "generated_at": generated_at,
        "available": bool(metrics),
        "metrics": metrics,
    }


def _build_city_map_details_snapshot(
    *,
    generated_at: str,
    frame: pd.DataFrame | None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    required_columns = {
        "city",
        "vacancy_count",
        "share",
        "role_distribution_json",
        "company_distribution_json",
        "work_mode_distribution_json",
    }
    if frame is not None and required_columns.issubset(frame.columns):
        for row in frame.to_dict(orient="records"):
            items.append(
                {
                    "city": _to_python_value(row.get("city")),
                    "vacancy_count": _to_python_value(row.get("vacancy_count")),
                    "share": _to_python_value(row.get("share")),
                    "role_distribution": _parse_json_array_value(row.get("role_distribution_json")),
                    "company_distribution": _parse_json_array_value(row.get("company_distribution_json")),
                    "work_mode_distribution": _parse_json_array_value(
                        row.get("work_mode_distribution_json")
                    ),
                }
            )
    return {
        "generated_at": generated_at,
        "available": bool(items),
        "items": items,
    }


def _build_top_skills_snapshot(
    *,
    generated_at: str,
    overall_frame: pd.DataFrame | None,
    by_role_category_frame: pd.DataFrame | None,
    by_canton_frame: pd.DataFrame | None,
    programming_languages_frame: pd.DataFrame | None,
    programming_languages_summary_frame: pd.DataFrame | None,
    frameworks_frame: pd.DataFrame | None,
    frameworks_summary_frame: pd.DataFrame | None,
) -> dict[str, Any]:
    available = any(
        frame is not None
        for frame in (
            overall_frame,
            by_role_category_frame,
            by_canton_frame,
            programming_languages_frame,
            programming_languages_summary_frame,
            frameworks_frame,
            frameworks_summary_frame,
        )
    )
    return {
        "generated_at": generated_at,
        "available": available,
        "overall": _frame_to_records(overall_frame),
        "by_role_category": _group_ranked_items(by_role_category_frame, "role_category"),
        "by_canton": _group_ranked_items(by_canton_frame, "canton"),
        "programming_languages": {
            "summary": _metric_frame_to_dict(programming_languages_summary_frame),
            "items": _frame_to_records(programming_languages_frame),
        },
        "frameworks_libraries": {
            "summary": _metric_frame_to_dict(frameworks_summary_frame),
            "items": _frame_to_records(frameworks_frame),
        },
    }


def _build_education_requirements_snapshot(
    *,
    generated_at: str,
    summary_frame: pd.DataFrame | None,
) -> dict[str, Any]:
    summary = _metric_frame_to_dict(summary_frame)
    return {
        "generated_at": generated_at,
        "available": bool(summary),
        "summary": summary,
    }


def _build_experience_requirements_snapshot(
    *,
    generated_at: str,
    summary_frame: pd.DataFrame | None,
    by_seniority_frame: pd.DataFrame | None,
) -> dict[str, Any]:
    summary = _metric_frame_to_dict(summary_frame)
    by_seniority = _frame_to_records(by_seniority_frame)
    return {
        "generated_at": generated_at,
        "available": bool(summary or by_seniority),
        "summary": summary,
        "by_seniority": by_seniority,
    }


def _build_vacancy_trends_snapshot(
    *,
    generated_at: str,
    summary_frame: pd.DataFrame | None,
    daily_frame: pd.DataFrame | None,
    weekly_frame: pd.DataFrame | None,
    monthly_frame: pd.DataFrame | None,
    daily_segments_frame: pd.DataFrame | None,
    weekly_segments_frame: pd.DataFrame | None,
) -> dict[str, Any]:
    summary = _metric_frame_to_dict(summary_frame)
    daily = _frame_to_records(daily_frame)
    weekly = _frame_to_records(weekly_frame)
    monthly = _frame_to_records(monthly_frame)
    daily_segments = _frame_to_records(daily_segments_frame)
    weekly_segments = _frame_to_records(weekly_segments_frame)
    return {
        "generated_at": generated_at,
        "available": bool(summary or daily or weekly or monthly or daily_segments or weekly_segments),
        "summary": summary,
        "daily": daily,
        "weekly": weekly,
        "segments": {
            "daily": daily_segments,
            "weekly": weekly_segments,
        },
        "seasonality": {
            "monthly": monthly,
        },
    }


def _build_salary_snapshot(
    *,
    generated_at: str,
    summary_frame: pd.DataFrame | None,
    by_role_category_frame: pd.DataFrame | None,
    by_seniority_frame: pd.DataFrame | None,
) -> dict[str, Any]:
    summary = _metric_frame_to_dict(summary_frame)
    by_role_category = _frame_to_records(by_role_category_frame)
    by_seniority = _frame_to_records(by_seniority_frame)
    return {
        "generated_at": generated_at,
        "available": bool(summary or by_role_category or by_seniority),
        "summary": summary,
        "by_role_category": by_role_category,
        "by_seniority": by_seniority,
    }


def _build_distribution_snapshot(
    *,
    generated_at: str,
    dimension: str,
    frame: pd.DataFrame | None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if frame is not None and dimension in frame.columns:
        items = [
            {
                "key": _to_python_value(row[dimension]),
                "label": _to_python_value(row[dimension]),
                "vacancy_count": _to_python_value(row.get("vacancy_count")),
                "share": _to_python_value(row.get("share")),
            }
            for row in frame.to_dict(orient="records")
        ]
    return {
        "generated_at": generated_at,
        "available": bool(items),
        "dimension": dimension,
        "items": items,
    }


def _build_items_snapshot(
    *,
    generated_at: str,
    frame: pd.DataFrame | None,
    items_key: str,
) -> dict[str, Any]:
    items = _frame_to_records(frame)
    return {
        "generated_at": generated_at,
        "available": bool(items),
        items_key: items,
    }


def _metric_frame_to_dict(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or not {"metric", "value"}.issubset(frame.columns):
        return {}
    return {
        str(row["metric"]): _normalize_metric_value(str(row["metric"]), row["value"])
        for row in frame.to_dict(orient="records")
    }


def _group_ranked_items(frame: pd.DataFrame | None, group_column: str) -> list[dict[str, Any]]:
    if frame is None or group_column not in frame.columns:
        return []

    groups: list[dict[str, Any]] = []
    grouped = frame.groupby(group_column, dropna=False, sort=True)
    for group_value, group_frame in grouped:
        items = _frame_to_records(group_frame.drop(columns=[group_column]))
        groups.append(
            {
                "group": _to_python_value(group_value),
                "items": items,
            }
        )
    return groups


def _frame_to_records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None:
        return []
    return [_clean_record(record) for record in frame.to_dict(orient="records")]


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: _to_python_value(value) for key, value in record.items()}


def _to_python_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass
    return value


def _coerce_numeric(value: Any) -> float | None:
    normalized = _to_python_value(value)
    if isinstance(normalized, bool) or normalized is None:
        return None
    if isinstance(normalized, (int, float)):
        return float(normalized)
    try:
        parsed = pd.to_numeric(normalized, errors="coerce")
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return float(parsed)


def _parse_json_array_value(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [_clean_record(item) for item in parsed if isinstance(item, dict)]


def _normalize_metric_value(metric_name: str, value: Any) -> Any:
    normalized = _to_python_value(value)
    numeric_metrics = {
        "salary_coverage",
        "vacancy_coverage",
        "higher_education_vacancy_share",
        "average_vacancies_per_company",
        "seniority_known_share",
        "experience_years_mentioned_share",
        "average_min_experience_years",
        "median_min_experience_years",
        "average_experience_years",
        "median_experience_years",
        "growth_30d",
        "growth_90d",
        "growth_180d",
        "growth_365d",
    }
    integer_metrics = {
        "total_vacancies",
        "total_companies",
        "higher_education_vacancy_count",
        "without_explicit_higher_education_count",
        "seniority_known_count",
        "experience_years_mentioned_count",
        "published_total",
        "closed_total",
        "published_30d",
        "published_90d",
        "published_180d",
        "published_365d",
        "published_previous_30d",
        "published_previous_90d",
        "published_previous_180d",
        "published_previous_365d",
        "distinct_items",
        "total_mentions",
        "vacancies_with_items",
        "salary_count",
        "average_salary",
        "median_salary",
        "p25_salary",
        "p75_salary",
        "min_salary",
        "max_salary",
    }
    if metric_name in {*integer_metrics, *numeric_metrics} and isinstance(normalized, str):
        numeric_value = pd.to_numeric(normalized, errors="coerce")
        if not pd.isna(numeric_value):
            normalized = numeric_value.item() if hasattr(numeric_value, "item") else numeric_value
    if (
        metric_name in integer_metrics
        and isinstance(normalized, float)
        and normalized.is_integer()
    ):
        return int(normalized)
    return normalized


def _clear_generated_files(directory: Path, pattern: str) -> None:
    for path in directory.glob(pattern):
        if path.is_file():
            path.unlink()

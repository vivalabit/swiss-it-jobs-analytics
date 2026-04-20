from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

EXPECTED_CSV_FILES: tuple[str, ...] = (
    "overview_metrics.csv",
    "salary_summary.csv",
    "salary_by_role_category.csv",
    "top_skills_overall.csv",
    "top_skills_by_role_category.csv",
    "top_skills_by_canton.csv",
    "top_programming_languages.csv",
    "programming_languages_summary.csv",
    "top_frameworks_libraries.csv",
    "frameworks_libraries_summary.csv",
    "distribution_role_category.csv",
    "distribution_city.csv",
    "distribution_canton.csv",
    "distribution_seniority.csv",
    "distribution_work_mode.csv",
    "skill_cooccurrence_pairs.csv",
)

DISTRIBUTION_DIMENSIONS: tuple[str, ...] = (
    "role_category",
    "city",
    "canton",
    "seniority",
    "work_mode",
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build compact public JSON snapshots from analytics CSV outputs.",
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=Path("analytics_output"),
        help="Directory containing analytics CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public_stats/data"),
        help="Directory where JSON snapshots will be written.",
    )
    parser.add_argument(
        "--copy-csv-dir",
        type=Path,
        default=Path("public_stats/csv"),
        help="Directory where source analytics CSV files will be copied.",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    snapshot_paths = build_public_snapshots(
        csv_dir=args.csv_dir,
        output_dir=args.output_dir,
        copy_csv_dir=args.copy_csv_dir,
    )
    print(f"Built {len(snapshot_paths)} public snapshot files in {args.output_dir.resolve()}")
    for path in snapshot_paths:
        print(path.resolve())
    return 0


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
            shutil.copy2(csv_dir / file_name, copy_csv_dir / file_name)

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
        "salary_metrics.json": _build_salary_snapshot(
            generated_at=generated_at,
            summary_frame=csv_frames["salary_summary.csv"],
            by_role_category_frame=csv_frames["salary_by_role_category.csv"],
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
    return frames


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
        "salary_metrics.json",
        "top_skills.json",
        "skill_pairs.json",
        *[f"distributions_{dimension}.json" for dimension in DISTRIBUTION_DIMENSIONS],
    ]
    return {
        "generated_at": generated_at,
        "schema_version": 2,
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


def _build_salary_snapshot(
    *,
    generated_at: str,
    summary_frame: pd.DataFrame | None,
    by_role_category_frame: pd.DataFrame | None,
) -> dict[str, Any]:
    summary = _metric_frame_to_dict(summary_frame)
    by_role_category = _frame_to_records(by_role_category_frame)
    return {
        "generated_at": generated_at,
        "available": bool(summary or by_role_category),
        "summary": summary,
        "by_role_category": by_role_category,
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


def _normalize_metric_value(metric_name: str, value: Any) -> Any:
    normalized = _to_python_value(value)
    numeric_metrics = {
        "salary_coverage",
        "vacancy_coverage",
        "average_vacancies_per_company",
    }
    integer_metrics = {
        "total_vacancies",
        "total_companies",
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


if __name__ == "__main__":
    raise SystemExit(main())

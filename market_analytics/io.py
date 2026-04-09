from __future__ import annotations

import ast
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from .constants import CANONICAL_COLUMN_ALIASES, MISSING_TEXT_VALUES, REQUIRED_COLUMNS


def load_dataset(dataset_path: str | Path) -> pd.DataFrame:
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".sqlite", ".db"}:
        return _load_dataset_from_sqlite(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    if suffix == ".json":
        try:
            return pd.read_json(path)
        except ValueError:
            return pd.read_json(path, lines=True)

    supported = ".csv, .parquet, .sqlite, .db, .json, .jsonl"
    raise ValueError(f"Unsupported dataset format '{suffix}'. Supported formats: {supported}")


def load_and_validate_dataset(dataset_path: str | Path) -> pd.DataFrame:
    dataset = load_dataset(dataset_path)
    return validate_and_standardize_dataset(dataset)


def validate_and_standardize_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        raise ValueError("The dataset is empty.")

    standardized = dataset.copy()
    normalized_columns = {
        column: _normalize_column_name(column) for column in standardized.columns
    }

    missing_required: list[str] = []
    for canonical_name in REQUIRED_COLUMNS:
        source_columns = _find_matching_columns(
            normalized_columns=normalized_columns,
            aliases=CANONICAL_COLUMN_ALIASES[canonical_name],
        )
        if not source_columns:
            missing_required.append(canonical_name)
            continue

        combined = _coalesce_columns(standardized, source_columns)
        if canonical_name == "skills":
            standardized[canonical_name] = combined
        else:
            standardized[canonical_name] = _clean_text_series(combined)

    optional_id_columns = _find_matching_columns(
        normalized_columns=normalized_columns,
        aliases=CANONICAL_COLUMN_ALIASES["vacancy_id"],
    )
    if optional_id_columns:
        standardized["vacancy_id"] = _clean_text_series(
            _coalesce_columns(standardized, optional_id_columns)
        )

    if missing_required:
        missing_list = ", ".join(sorted(missing_required))
        raise ValueError(
            "Dataset is missing required columns after alias resolution: "
            f"{missing_list}"
        )

    standardized["skills_list"] = standardized["skills"].map(parse_skills)
    return standardized


def parse_skills(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []

    raw_items: list[Any]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.casefold() in MISSING_TEXT_VALUES:
            return []

        parsed_json = _parse_list_like_string(stripped)
        if parsed_json is not None:
            raw_items = parsed_json
        else:
            raw_items = re.split(r"[,\n;|]+", stripped)
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]

    seen: set[str] = set()
    parsed_skills: list[str] = []
    for item in raw_items:
        normalized = _normalize_skill(item)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        parsed_skills.append(normalized)
    return parsed_skills


def _parse_list_like_string(value: str) -> list[Any] | None:
    if not value.startswith("[") or not value.endswith("]"):
        return None

    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, list):
            return parsed
    return None


def _normalize_skill(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None

    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.casefold() in MISSING_TEXT_VALUES:
        return None
    return text.casefold()


def _normalize_column_name(column_name: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(column_name).strip().casefold())
    return normalized.strip("_")


def _find_matching_columns(
    normalized_columns: dict[str, str],
    aliases: tuple[str, ...],
) -> list[str]:
    normalized_aliases = {_normalize_column_name(alias) for alias in aliases}
    return [
        original_name
        for original_name, normalized_name in normalized_columns.items()
        if normalized_name in normalized_aliases
    ]


def _coalesce_columns(dataset: pd.DataFrame, columns: list[str]) -> pd.Series:
    if len(columns) == 1:
        return dataset[columns[0]]
    return dataset[columns].bfill(axis=1).iloc[:, 0]


def _clean_text_series(series: pd.Series) -> pd.Series:
    return series.map(_normalize_text_value)


def _normalize_text_value(value: Any) -> Any:
    if value is None:
        return pd.NA
    if isinstance(value, float) and pd.isna(value):
        return pd.NA

    if isinstance(value, str):
        normalized = re.sub(r"\s+", " ", value).strip()
        if normalized.casefold() in MISSING_TEXT_VALUES:
            return pd.NA
        return normalized
    return value


def _load_dataset_from_sqlite(path: Path) -> pd.DataFrame:
    connection = sqlite3.connect(path)
    try:
        query = """
        SELECT
            vacancy_id,
            company,
            place,
            analytics_json
        FROM vacancies
        """
        dataset = pd.read_sql_query(query, connection)
    finally:
        connection.close()

    if dataset.empty:
        return dataset

    analytics_payloads = dataset["analytics_json"].map(_parse_json_object)
    records = [
        _build_record_from_sqlite_row(row, analytics)
        for (_, row), analytics in zip(dataset.iterrows(), analytics_payloads, strict=False)
    ]
    return pd.DataFrame.from_records(records)


def _parse_json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _build_record_from_sqlite_row(
    row: pd.Series,
    analytics: dict[str, Any],
) -> dict[str, Any]:
    location = analytics.get("job_location")
    company_info = analytics.get("company")
    seniority_labels = analytics.get("seniority_labels")

    return {
        "vacancy_id": row.get("vacancy_id"),
        "company": row.get("company") or _nested_value(company_info, "name"),
        "role_category": analytics.get("role_family_primary"),
        "city": _nested_value(location, "locality") or row.get("place"),
        "canton": _nested_value(location, "region"),
        "seniority": _first_list_item(seniority_labels),
        "work_mode": analytics.get("remote_mode"),
        "skills": _collect_skills_from_analytics(analytics),
    }


def _nested_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _first_list_item(value: Any) -> Any:
    if isinstance(value, list) and value:
        return value[0]
    return None


def _collect_skills_from_analytics(analytics: dict[str, Any]) -> list[str]:
    skill_fields = (
        "programming_languages",
        "frameworks_libraries",
        "cloud_platforms",
        "data_platforms",
        "databases",
        "tools_platforms",
        "methodologies",
    )
    skills: list[str] = []
    for field_name in skill_fields:
        value = analytics.get(field_name)
        if isinstance(value, list):
            skills.extend(value)
    return skills

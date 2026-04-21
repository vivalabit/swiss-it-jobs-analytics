from __future__ import annotations

import ast
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .constants import (
    CANONICAL_COLUMN_ALIASES,
    MISSING_TEXT_VALUES,
    OPTIONAL_LIST_COLUMNS,
    REQUIRED_COLUMNS,
)

CANTON_CODES: frozenset[str] = frozenset(
    {
        "AG",
        "AI",
        "AR",
        "BE",
        "BL",
        "BS",
        "FR",
        "GE",
        "GL",
        "GR",
        "JU",
        "LU",
        "NE",
        "NW",
        "OW",
        "SG",
        "SH",
        "SO",
        "SZ",
        "TG",
        "TI",
        "UR",
        "VD",
        "VS",
        "ZG",
        "ZH",
    }
)

CANTON_NAME_TO_CODE: dict[str, str] = {
    "aargau": "AG",
    "appenzell innerrhoden": "AI",
    "appenzell ausserrhoden": "AR",
    "bern": "BE",
    "berne": "BE",
    "basel landschaft": "BL",
    "basel land": "BL",
    "basel stadt": "BS",
    "fribourg": "FR",
    "freiburg": "FR",
    "geneva": "GE",
    "geneve": "GE",
    "glarus": "GL",
    "graubunden": "GR",
    "grisons": "GR",
    "jura": "JU",
    "lucerne": "LU",
    "luzern": "LU",
    "neuchatel": "NE",
    "nidwalden": "NW",
    "obwalden": "OW",
    "st gallen": "SG",
    "saint gallen": "SG",
    "schaffhausen": "SH",
    "solothurn": "SO",
    "schwyz": "SZ",
    "thurgau": "TG",
    "ticino": "TI",
    "uri": "UR",
    "vaud": "VD",
    "valais": "VS",
    "wallis": "VS",
    "zug": "ZG",
    "zurich": "ZH",
    "zuerich": "ZH",
}

CITY_DISPLAY_ALIASES: dict[str, str] = {
    "zurich": "Zürich",
    "zuerich": "Zürich",
    "geneva": "Genève",
    "geneve": "Genève",
    "lucerne": "Luzern",
    "basle": "Basel",
    "neuchatel": "Neuchâtel",
}

CITY_TO_CANTON: dict[str, str] = {
    "aarau": "AG",
    "aadorf": "TG",
    "arlesheim": "BL",
    "baden": "AG",
    "baar": "ZG",
    "basel": "BS",
    "bern": "BE",
    "biel": "BE",
    "biel bienne": "BE",
    "bulle": "FR",
    "chiasso": "TI",
    "dietikon": "ZH",
    "duebendorf": "ZH",
    "dubendorf": "ZH",
    "ecublens": "VD",
    "emmen": "LU",
    "frauenfeld": "TG",
    "fribourg": "FR",
    "freiburg": "FR",
    "gerlafingen": "SO",
    "geneva": "GE",
    "genève": "GE",
    "geneve": "GE",
    "glattpark": "ZH",
    "heerbrugg": "SG",
    "hinwil": "ZH",
    "jona": "SG",
    "koniz": "BE",
    "köniz": "BE",
    "kriens": "LU",
    "lausanne": "VD",
    "lugano": "TI",
    "luzern": "LU",
    "lucerne": "LU",
    "meyrin": "GE",
    "moosseedorf": "BE",
    "munchenstein": "BL",
    "münchenstein": "BL",
    "neuchatel": "NE",
    "neuchâtel": "NE",
    "nyon": "VD",
    "olten": "SO",
    "ostermundigen": "BE",
    "otelfingen": "ZH",
    "renens": "VD",
    "rotkreuz": "ZG",
    "rothenburg": "LU",
    "rapperswil": "SG",
    "rapperswil jona": "SG",
    "reinach": "BL",
    "rheinfelden": "AG",
    "schaffhausen": "SH",
    "schlieren": "ZH",
    "sempach": "LU",
    "sion": "VS",
    "solothurn": "SO",
    "spreitenbach": "AG",
    "st gallen": "SG",
    "saint gallen": "SG",
    "thunersee": "BE",
    "thun": "BE",
    "winterthur": "ZH",
    "yverdon": "VD",
    "zug": "ZG",
    "zwingen": "BL",
    "cham": "ZG",
    "bulach": "ZH",
    "bülach": "ZH",
    "bubendorf": "BL",
    "domat ems": "GR",
    "nottwil": "LU",
    "thun gwatt": "BE",
    "zurich flughafen": "ZH",
    "zurich": "ZH",
    "zürich": "ZH",
}


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


def load_datasets(dataset_paths: Iterable[str | Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for dataset_path in dataset_paths:
        frames.append(load_dataset(dataset_path))

    if not frames:
        raise ValueError("At least one dataset path is required.")
    if len(frames) == 1:
        return frames[0]

    combined = pd.concat(frames, ignore_index=True, sort=False)
    dedupe_columns = [column for column in ("source", "vacancy_id") if column in combined.columns]
    if dedupe_columns:
        combined = combined.drop_duplicates(subset=dedupe_columns, keep="first").reset_index(drop=True)
    return combined


def load_and_validate_dataset(dataset_path: str | Path) -> pd.DataFrame:
    dataset = load_dataset(dataset_path)
    return validate_and_standardize_dataset(dataset)


def load_and_validate_datasets(dataset_paths: Iterable[str | Path]) -> pd.DataFrame:
    dataset = load_datasets(dataset_paths)
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

    for canonical_name in ("salary_min", "salary_max"):
        source_columns = _find_matching_columns(
            normalized_columns=normalized_columns,
            aliases=CANONICAL_COLUMN_ALIASES[canonical_name],
        )
        if source_columns:
            standardized[canonical_name] = pd.to_numeric(
                _coalesce_columns(standardized, source_columns),
                errors="coerce",
            )
        else:
            standardized[canonical_name] = pd.Series(pd.NA, index=standardized.index)

    for canonical_name in ("salary_currency", "salary_unit", "salary_text"):
        source_columns = _find_matching_columns(
            normalized_columns=normalized_columns,
            aliases=CANONICAL_COLUMN_ALIASES[canonical_name],
        )
        if source_columns:
            standardized[canonical_name] = _clean_text_series(
                _coalesce_columns(standardized, source_columns)
            )
        else:
            standardized[canonical_name] = pd.Series(pd.NA, index=standardized.index)

    standardized["salary_currency"] = standardized["salary_currency"].map(_uppercase_text_value)
    standardized["salary_unit"] = standardized["salary_unit"].map(_uppercase_text_value)

    if missing_required:
        missing_list = ", ".join(sorted(missing_required))
        raise ValueError(
            "Dataset is missing required columns after alias resolution: "
            f"{missing_list}"
        )

    standardized["skills_list"] = standardized["skills"].map(parse_skills)
    standardized["city"] = standardized["city"].map(_normalize_city_value)
    standardized["canton"] = standardized.apply(
        lambda row: _normalize_canton_value(
            row.get("canton"),
            city=row.get("city"),
        ),
        axis=1,
    )
    for canonical_name in OPTIONAL_LIST_COLUMNS:
        source_columns = _find_matching_columns(
            normalized_columns=normalized_columns,
            aliases=CANONICAL_COLUMN_ALIASES[canonical_name],
        )
        if source_columns:
            combined = _coalesce_columns(standardized, source_columns)
            standardized[canonical_name] = combined
        else:
            standardized[canonical_name] = _empty_list_series(standardized.index)
        standardized[f"{canonical_name}_list"] = standardized[canonical_name].map(parse_skills)
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


def _uppercase_text_value(value: Any) -> Any:
    text = _normalize_text_value(value)
    if text is pd.NA:
        return pd.NA
    return str(text).upper()


def _empty_list_series(index: pd.Index) -> pd.Series:
    return pd.Series([[] for _ in index], index=index, dtype="object")


def _load_dataset_from_sqlite(path: Path) -> pd.DataFrame:
    connection = sqlite3.connect(path)
    try:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(vacancies)").fetchall()
        }
        source_select = "source" if "source" in columns else "NULL AS source"
        title_select = "title" if "title" in columns else "NULL AS title"
        description_text_select = (
            "description_text" if "description_text" in columns else "NULL AS description_text"
        )
        publication_date_select = (
            "publication_date" if "publication_date" in columns else "NULL AS publication_date"
        )
        first_seen_at_select = "first_seen_at" if "first_seen_at" in columns else "NULL AS first_seen_at"
        last_seen_at_select = "last_seen_at" if "last_seen_at" in columns else "NULL AS last_seen_at"
        salary_selects = {
            column: column if column in columns else f"NULL AS {column}"
            for column in (
                "salary_min",
                "salary_max",
                "salary_currency",
                "salary_unit",
                "salary_text",
            )
        }
        query = """
        SELECT
            vacancy_id,
            {source_select},
            {title_select},
            company,
            place,
            {publication_date_select},
            {first_seen_at_select},
            {last_seen_at_select},
            {description_text_select},
            analytics_json,
            {salary_min},
            {salary_max},
            {salary_currency},
            {salary_unit},
            {salary_text}
        FROM vacancies
        """.format(
            source_select=source_select,
            title_select=title_select,
            description_text_select=description_text_select,
            publication_date_select=publication_date_select,
            first_seen_at_select=first_seen_at_select,
            last_seen_at_select=last_seen_at_select,
            **salary_selects,
        )
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
    experience_years = analytics.get("experience_years")
    locality = _nested_value(location, "locality") or row.get("place")
    postal_code = _nested_value(location, "postal_code")
    region = _nested_value(location, "region")

    return {
        "vacancy_id": row.get("vacancy_id"),
        "source": row.get("source"),
        "title": row.get("title"),
        "publication_date": row.get("publication_date"),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
        "company": row.get("company") or _nested_value(company_info, "name"),
        "role_category": analytics.get("role_family_primary"),
        "city": _normalize_city_value(locality),
        "canton": _derive_canton(
            region=region,
            locality=locality,
            place=row.get("place"),
            postal_code=postal_code,
        ),
        "seniority": _select_seniority_label(seniority_labels, title=row.get("title")),
        "experience_years_min": _nested_value(experience_years, "min"),
        "experience_years_max": _nested_value(experience_years, "max"),
        "work_mode": analytics.get("remote_mode"),
        "programming_languages": analytics.get("programming_languages", []),
        "frameworks_libraries": analytics.get("frameworks_libraries", []),
        "skills": _collect_skills_from_analytics(analytics),
        "salary_min": row.get("salary_min"),
        "salary_max": row.get("salary_max"),
        "salary_currency": row.get("salary_currency"),
        "salary_unit": row.get("salary_unit"),
        "salary_text": row.get("salary_text"),
        "description_text": row.get("description_text"),
    }


def _nested_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _first_list_item(value: Any) -> Any:
    if isinstance(value, list) and value:
        return value[0]
    return None


def _select_seniority_label(value: Any, *, title: Any = None) -> Any:
    if not isinstance(value, list) or not value:
        return None

    labels = [str(item).casefold() for item in value if item]
    if not labels:
        return None

    title_key = _normalize_lookup_key(title) if title is not None else ""
    title_matches = [
        label
        for label, pattern in (
            ("manager", r"\b(?:manager|lead|leiter|responsable|head)\b"),
            ("senior", r"\b(?:senior|staff|principal|architect|expert)\b"),
            ("junior", r"\b(?:junior|graduate|entry)\b"),
            ("intern", r"\b(?:intern|internship|trainee|werkstudent|student)\b"),
            ("mid", r"\b(?:mid|professional)\b"),
        )
        if label in labels and re.search(pattern, title_key)
    ]
    if len(title_matches) == 1:
        return title_matches[0]
    if len(title_matches) > 1:
        return pd.NA

    if labels == ["intern"]:
        return pd.NA

    for label in ("manager", "senior", "mid", "junior", "intern"):
        if label in labels:
            if label == "intern":
                continue
            return label
    return labels[0]


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


def _normalize_city_value(value: Any) -> Any:
    text = _normalize_text_value(value)
    if text is pd.NA:
        return pd.NA
    clean_text = re.sub(r"^\d{4}\s*/?\s*", "", str(text)).strip()
    match = re.match(r"^(.*?)(?:\s+([A-Z]{2}))?$", clean_text)
    if match:
        base_name = match.group(1).strip()
        suffix = match.group(2)
        if suffix in CANTON_CODES:
            clean_text = base_name

    normalized_key = _normalize_lookup_key(clean_text)
    return CITY_DISPLAY_ALIASES.get(normalized_key, clean_text)


def _normalize_canton_value(
    value: Any,
    *,
    city: Any = None,
) -> Any:
    text = _normalize_text_value(value)
    if text is pd.NA:
        if city is None or city is pd.NA:
            return pd.NA
        return _derive_canton(region=None, locality=city, place=city, postal_code=None)

    raw_text = str(text).strip()
    upper_text = raw_text.upper()
    if upper_text in CANTON_CODES:
        return upper_text

    normalized_key = _normalize_lookup_key(raw_text)
    if normalized_key in CANTON_NAME_TO_CODE:
        return CANTON_NAME_TO_CODE[normalized_key]

    if city is not None and city is not pd.NA:
        derived = _derive_canton(region=raw_text, locality=city, place=city, postal_code=None)
        if derived is not None and derived is not pd.NA:
            return derived
    return raw_text


def _derive_canton(
    *,
    region: Any,
    locality: Any,
    place: Any,
    postal_code: Any,
) -> Any:
    region_code = _extract_canton_code(region)
    if region_code:
        return region_code

    for candidate in (locality, place):
        inline_code = _extract_any_canton_code(candidate)
        if inline_code:
            return inline_code

    for candidate in (locality, place):
        suffix_code = _extract_canton_suffix(candidate)
        if suffix_code:
            return suffix_code

    for candidate in (locality, place):
        locality_postal_code = _extract_postal_code_from_text(candidate)
        if locality_postal_code:
            postal_code_value = _postal_code_to_canton(locality_postal_code)
            if postal_code_value:
                return postal_code_value

    for candidate in (locality, place):
        city_code = _map_city_to_canton(candidate)
        if city_code:
            return city_code

    postal_code_value = _postal_code_to_canton(postal_code)
    if postal_code_value:
        return postal_code_value
    return pd.NA


def _extract_canton_code(value: Any) -> str | None:
    text = _normalize_text_value(value)
    if text is pd.NA:
        return None
    raw_text = str(text).strip()
    upper_text = raw_text.upper()
    if upper_text in CANTON_CODES:
        return upper_text
    normalized_key = _normalize_lookup_key(raw_text)
    return CANTON_NAME_TO_CODE.get(normalized_key)


def _extract_canton_suffix(value: Any) -> str | None:
    text = _normalize_text_value(value)
    if text is pd.NA:
        return None
    match = re.search(r"\b([A-Z]{2})$", str(text).strip())
    if not match:
        return None
    suffix = match.group(1).upper()
    if suffix in CANTON_CODES:
        return suffix
    return None


def _extract_any_canton_code(value: Any) -> str | None:
    text = _normalize_text_value(value)
    if text is pd.NA:
        return None
    codes = {
        token.upper()
        for token in re.findall(r"\b[A-Z]{2}\b", str(text))
        if token.upper() in CANTON_CODES
    }
    if len(codes) == 1:
        return next(iter(codes))
    return None


def _map_city_to_canton(value: Any) -> str | None:
    text = _normalize_city_value(value)
    if text is pd.NA:
        return None
    normalized_key = _normalize_lookup_key(text)
    exact_match = CITY_TO_CANTON.get(normalized_key)
    if exact_match:
        return exact_match

    matched_cantons = {
        canton
        for city_name, canton in CITY_TO_CANTON.items()
        if re.search(rf"\b{re.escape(city_name)}\b", normalized_key)
    }
    if len(matched_cantons) == 1:
        return next(iter(matched_cantons))
    return None


def _postal_code_to_canton(value: Any) -> str | None:
    text = _normalize_text_value(value)
    if text is pd.NA:
        return None
    digits = re.sub(r"[^0-9]", "", str(text))
    if len(digits) < 4:
        return None

    postal_code = int(digits[:4])
    for lower, upper, canton in _postal_code_ranges():
        if lower <= postal_code <= upper:
            return canton
    return None


def _extract_postal_code_from_text(value: Any) -> str | None:
    text = _normalize_text_value(value)
    if text is pd.NA:
        return None
    match = re.search(r"\b(\d{4})\b", str(text))
    if not match:
        return None
    return match.group(1)


def _postal_code_ranges() -> tuple[tuple[int, int, str], ...]:
    return (
        (1000, 1199, "VD"),
        (1200, 1299, "GE"),
        (1400, 1499, "VD"),
        (1500, 1799, "FR"),
        (1800, 1999, "VS"),
        (2000, 2999, "NE"),
        (3000, 3999, "BE"),
        (4000, 4299, "BS"),
        (4300, 4499, "BL"),
        (4500, 4999, "SO"),
        (5000, 5799, "AG"),
        (6000, 6199, "LU"),
        (6200, 6499, "LU"),
        (6500, 6999, "TI"),
        (7000, 7799, "GR"),
        (8000, 8799, "ZH"),
        (8800, 8899, "SZ"),
        (9000, 9299, "SG"),
        (9300, 9399, "TG"),
        (9400, 9499, "SG"),
        (9500, 9999, "SG"),
    )


def _normalize_lookup_key(value: Any) -> str:
    text = str(value).strip().casefold()
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_text)).strip()

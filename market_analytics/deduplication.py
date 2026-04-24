from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

LIST_COLUMNS: tuple[tuple[str, str], ...] = (
    ("skills", "skills_list"),
    ("programming_languages", "programming_languages_list"),
    ("frameworks_libraries", "frameworks_libraries_list"),
)
COMPANY_SUFFIX_TOKENS: frozenset[str] = frozenset(
    {
        "ag",
        "gmbh",
        "sa",
        "sarl",
        "sas",
        "ltd",
        "llc",
        "inc",
        "corp",
        "co",
        "company",
        "group",
        "holding",
        "holdings",
        "bv",
        "nv",
        "plc",
    }
)
TITLE_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "the",
        "to",
        "with",
        "im",
        "of",
        "fuer",
        "fur",
        "und",
        "et",
        "de",
        "du",
    }
)
DESCRIPTION_STOPWORDS: frozenset[str] = TITLE_STOPWORDS | frozenset(
    {
        "are",
        "as",
        "be",
        "build",
        "can",
        "experience",
        "have",
        "is",
        "our",
        "role",
        "team",
        "that",
        "this",
        "we",
        "will",
        "you",
        "your",
    }
)
MAX_PUBLICATION_DATE_GAP_DAYS = 14


@dataclass(frozen=True, slots=True)
class _MatchFeatures:
    title_score: float
    description_score: float
    location_score: float
    role_score: float
    seniority_score: float
    work_mode_score: float
    date_score: float

    @property
    def total_score(self) -> float:
        return (
            self.title_score * 0.45
            + self.location_score * 0.2
            + self.date_score * 0.15
            + self.description_score * 0.1
            + self.role_score * 0.05
            + self.seniority_score * 0.025
            + self.work_mode_score * 0.025
        )


def deduplicate_cross_source_vacancies(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty or "source" not in dataset.columns or "company" not in dataset.columns:
        return dataset.copy()

    prepared, groups = _cluster_dataset(dataset)

    merged_rows: list[pd.Series] = []
    ordering: list[int] = []
    for root, positions in groups.items():
        cluster = prepared.loc[positions]
        merged = _merge_cluster(cluster, group_number=len(merged_rows) + 1)
        merged_rows.append(merged)
        ordering.append(int(cluster["_dedupe_original_index"].min()))

    if not merged_rows:
        return dataset.copy().reset_index(drop=True)

    merged_frame = pd.DataFrame(merged_rows)
    merged_frame["_dedupe_sort_order"] = ordering
    merged_frame = merged_frame.sort_values("_dedupe_sort_order").reset_index(drop=True)

    helper_columns = [column for column in merged_frame.columns if column.startswith("_dedupe_")]
    return merged_frame.drop(columns=helper_columns, errors="ignore")


def build_cross_source_dedup_report(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty or "source" not in dataset.columns or "company" not in dataset.columns:
        return pd.DataFrame(
            columns=[
                "duplicate_group_id",
                "vacancy_id",
                "source",
                "company",
                "title",
                "city",
                "canton",
                "publication_date",
                "is_canonical",
                "canonical_vacancy_id",
                "canonical_source",
                "duplicate_vacancy_count",
                "duplicate_source_count",
            ]
        )

    prepared, groups = _cluster_dataset(dataset)
    rows: list[dict[str, Any]] = []
    group_number = 0
    for positions in groups.values():
        if len(positions) <= 1:
            continue

        group_number += 1
        duplicate_group_id = f"cross-source-{group_number:05d}"
        cluster = prepared.loc[positions]
        canonical_index = _select_canonical_index(cluster)
        canonical_row = cluster.loc[canonical_index]
        duplicate_sources = _sorted_non_empty_unique(cluster["source"].tolist())

        for position in positions:
            row = cluster.loc[position]
            rows.append(
                {
                    "duplicate_group_id": duplicate_group_id,
                    "vacancy_id": row.get("vacancy_id"),
                    "source": row.get("source"),
                    "company": row.get("company"),
                    "title": row.get("title"),
                    "city": row.get("city"),
                    "canton": row.get("canton"),
                    "publication_date": row.get("publication_date"),
                    "is_canonical": position == canonical_index,
                    "canonical_vacancy_id": canonical_row.get("vacancy_id"),
                    "canonical_source": canonical_row.get("source"),
                    "duplicate_vacancy_count": len(cluster),
                    "duplicate_source_count": len(duplicate_sources),
                }
            )

    report = pd.DataFrame.from_records(rows)
    if report.empty:
        return report
    return report.sort_values(
        ["duplicate_group_id", "is_canonical", "source", "vacancy_id"],
        ascending=[True, False, True, True],
    ).reset_index(drop=True)


def _build_match_features(left_row: pd.Series, right_row: pd.Series) -> _MatchFeatures:
    return _MatchFeatures(
        title_score=_title_similarity(left_row, right_row),
        description_score=_description_similarity(left_row, right_row),
        location_score=_location_similarity(left_row, right_row),
        role_score=_exact_match_score(
            left_row.get("_dedupe_role_key"),
            right_row.get("_dedupe_role_key"),
        ),
        seniority_score=_exact_match_score(
            left_row.get("_dedupe_seniority_key"),
            right_row.get("_dedupe_seniority_key"),
        ),
        work_mode_score=_exact_match_score(
            left_row.get("_dedupe_work_mode_key"),
            right_row.get("_dedupe_work_mode_key"),
        ),
        date_score=_date_similarity(
            left_row.get("_dedupe_publication_date"),
            right_row.get("_dedupe_publication_date"),
        ),
    )


def _passes_hard_filters(left_row: pd.Series, right_row: pd.Series) -> bool:
    left_date = left_row.get("_dedupe_publication_date")
    right_date = right_row.get("_dedupe_publication_date")
    if pd.notna(left_date) and pd.notna(right_date):
        if abs((left_date - right_date).days) > MAX_PUBLICATION_DATE_GAP_DAYS:
            return False

    left_canton = left_row.get("_dedupe_canton_key")
    right_canton = right_row.get("_dedupe_canton_key")
    left_city = left_row.get("_dedupe_city_key")
    right_city = right_row.get("_dedupe_city_key")
    if left_canton and right_canton and left_canton != right_canton:
        if not (left_city and right_city and left_city == right_city):
            return False

    return _title_similarity(left_row, right_row) >= 0.72


def _is_cross_source_duplicate(features: _MatchFeatures) -> bool:
    if features.title_score < 0.72:
        return False
    if features.location_score < 0.5:
        return False
    return features.total_score >= 0.82


def _merge_cluster(cluster: pd.DataFrame, *, group_number: int) -> pd.Series:
    canonical_index = _select_canonical_index(cluster)
    merged = cluster.loc[canonical_index].copy()
    cluster_size = len(cluster)
    duplicate_sources = _sorted_non_empty_unique(cluster["source"].tolist()) if "source" in cluster else []

    merged["duplicate_group_id"] = f"cross-source-{group_number:05d}"
    merged["is_cross_source_duplicate"] = cluster_size > 1
    merged["duplicate_source_count"] = len(duplicate_sources)
    merged["duplicate_sources"] = duplicate_sources
    merged["duplicate_vacancy_count"] = cluster_size
    merged["first_seen_at"] = _earliest_value(cluster.get("first_seen_at"))
    merged["last_seen_at"] = _latest_value(cluster.get("last_seen_at"))
    merged["publication_date"] = _earliest_value(cluster.get("publication_date"))
    merged["description_text"] = _longest_text(cluster.get("description_text"))
    merged["salary_text"] = _longest_text(cluster.get("salary_text"))

    for raw_column, parsed_column in LIST_COLUMNS:
        if parsed_column not in cluster.columns:
            continue
        merged_list = _merge_list_values(cluster[parsed_column])
        merged[parsed_column] = merged_list
        if raw_column in cluster.columns:
            merged[raw_column] = merged_list

    return merged


def _cluster_dataset(dataset: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, list[int]]]:
    prepared = dataset.copy()
    prepared["_dedupe_original_index"] = range(len(prepared))
    prepared["_dedupe_company_key"] = prepared["company"].map(_normalize_company_key)
    prepared["_dedupe_title_key"] = prepared.get("title", pd.Series(pd.NA, index=prepared.index)).map(
        _normalize_text_key
    )
    prepared["_dedupe_title_tokens"] = prepared["_dedupe_title_key"].map(
        lambda value: _tokenize(value, stopwords=TITLE_STOPWORDS)
    )
    prepared["_dedupe_city_key"] = prepared.get("city", pd.Series(pd.NA, index=prepared.index)).map(
        _normalize_text_key
    )
    prepared["_dedupe_canton_key"] = prepared.get(
        "canton", pd.Series(pd.NA, index=prepared.index)
    ).map(_normalize_canton_key)
    prepared["_dedupe_role_key"] = prepared.get(
        "role_category", pd.Series(pd.NA, index=prepared.index)
    ).map(_normalize_text_key)
    prepared["_dedupe_seniority_key"] = prepared.get(
        "seniority", pd.Series(pd.NA, index=prepared.index)
    ).map(_normalize_text_key)
    prepared["_dedupe_work_mode_key"] = prepared.get(
        "work_mode", pd.Series(pd.NA, index=prepared.index)
    ).map(_normalize_text_key)
    prepared["_dedupe_description_tokens"] = prepared.get(
        "description_text", pd.Series(pd.NA, index=prepared.index)
    ).map(_description_tokens)
    prepared["_dedupe_publication_date"] = _coalesce_datetime_columns(prepared)

    parent = list(range(len(prepared)))

    company_groups = prepared.groupby("_dedupe_company_key", dropna=False).groups
    for company_key, row_indexes in company_groups.items():
        if not isinstance(company_key, str) or not company_key:
            continue
        positions = list(row_indexes)
        for left_offset, left_position in enumerate(positions):
            left_row = prepared.loc[left_position]
            for right_position in positions[left_offset + 1 :]:
                right_row = prepared.loc[right_position]
                if _normalize_text_key(left_row.get("source")) == _normalize_text_key(
                    right_row.get("source")
                ):
                    continue
                if not _passes_hard_filters(left_row, right_row):
                    continue
                features = _build_match_features(left_row, right_row)
                if _is_cross_source_duplicate(features):
                    _union(parent, left_position, right_position)

    groups: dict[int, list[int]] = {}
    for position in range(len(prepared)):
        root = _find(parent, position)
        groups.setdefault(root, []).append(position)

    return prepared, groups


def _select_canonical_index(cluster: pd.DataFrame) -> int:
    return max(
        cluster.index,
        key=lambda index: _row_completeness_score(cluster.loc[index]),
    )


def _row_completeness_score(row: pd.Series) -> tuple[int, int, int]:
    filled_columns = 0
    for value in row.tolist():
        if _has_value(value):
            filled_columns += 1

    description_length = len(str(row.get("description_text") or ""))
    list_items = 0
    for _, parsed_column in LIST_COLUMNS:
        list_items += len(_as_list(row.get(parsed_column)))
    return filled_columns, description_length, list_items


def _title_similarity(left_row: pd.Series, right_row: pd.Series) -> float:
    left_key = left_row.get("_dedupe_title_key")
    right_key = right_row.get("_dedupe_title_key")
    if not left_key or not right_key:
        return 0.0

    sequence_score = SequenceMatcher(None, left_key, right_key).ratio()
    token_score = _jaccard_similarity(
        left_row.get("_dedupe_title_tokens"),
        right_row.get("_dedupe_title_tokens"),
    )
    return max(sequence_score, token_score)


def _description_similarity(left_row: pd.Series, right_row: pd.Series) -> float:
    left_tokens = left_row.get("_dedupe_description_tokens")
    right_tokens = right_row.get("_dedupe_description_tokens")
    if not left_tokens or not right_tokens:
        return 0.5
    return _jaccard_similarity(left_tokens, right_tokens)


def _location_similarity(left_row: pd.Series, right_row: pd.Series) -> float:
    left_city = left_row.get("_dedupe_city_key")
    right_city = right_row.get("_dedupe_city_key")
    if left_city and right_city and left_city == right_city:
        return 1.0

    left_canton = left_row.get("_dedupe_canton_key")
    right_canton = right_row.get("_dedupe_canton_key")
    if left_canton and right_canton and left_canton == right_canton:
        return 0.8
    if (left_city and not right_city) or (right_city and not left_city):
        return 0.6
    if (left_canton and not right_canton) or (right_canton and not left_canton):
        return 0.55
    return 0.5


def _date_similarity(left_value: Any, right_value: Any) -> float:
    if pd.isna(left_value) or pd.isna(right_value):
        return 0.5

    distance = abs((left_value - right_value).days)
    if distance == 0:
        return 1.0
    if distance <= 3:
        return 0.9
    if distance <= 7:
        return 0.75
    if distance <= MAX_PUBLICATION_DATE_GAP_DAYS:
        return 0.6
    return 0.0


def _exact_match_score(left_value: Any, right_value: Any) -> float:
    if not left_value or not right_value:
        return 0.5
    return 1.0 if left_value == right_value else 0.0


def _coalesce_datetime_columns(dataset: pd.DataFrame) -> pd.Series:
    candidates = []
    for column in ("publication_date", "first_seen_at", "last_seen_at"):
        if column in dataset.columns:
            candidates.append(_parse_datetime_series(dataset[column]).dt.normalize())
    if not candidates:
        return pd.Series(pd.NaT, index=dataset.index)

    combined = candidates[0]
    for candidate in candidates[1:]:
        combined = combined.fillna(candidate)
    return combined


def _normalize_company_key(value: Any) -> str:
    normalized = _normalize_text_key(value)
    if not normalized:
        return ""

    tokens = [token for token in normalized.split() if token not in COMPANY_SUFFIX_TOKENS]
    return " ".join(tokens)


def _normalize_canton_key(value: Any) -> str:
    normalized = _normalize_text_key(value)
    return normalized.upper() if normalized else ""


def _normalize_text_key(value: Any) -> str:
    if value is None or value is pd.NA:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""

    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _description_tokens(value: Any) -> set[str]:
    normalized = _normalize_text_key(value)
    return _tokenize(normalized, stopwords=DESCRIPTION_STOPWORDS, minimum_length=4)


def _tokenize(
    value: str,
    *,
    stopwords: frozenset[str],
    minimum_length: int = 2,
) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in value.split()
        if len(token) >= minimum_length and token not in stopwords
    }


def _jaccard_similarity(left_tokens: Any, right_tokens: Any) -> float:
    left_set = set(left_tokens or [])
    right_set = set(right_tokens or [])
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _merge_list_values(values: pd.Series) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values.tolist():
        for item in _as_list(value):
            normalized = _normalize_text_key(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(str(item))
    return merged


def _as_list(value: Any) -> list[Any]:
    if value is None or value is pd.NA:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _longest_text(series: pd.Series | None) -> Any:
    if series is None:
        return pd.NA
    texts = [str(value).strip() for value in series.tolist() if _has_value(value)]
    if not texts:
        return pd.NA
    return max(texts, key=len)


def _earliest_value(series: pd.Series | None) -> Any:
    if series is None:
        return pd.NA
    datetimes = _parse_datetime_series(series)
    if datetimes.notna().any():
        return datetimes.min().isoformat()
    values = [value for value in series.tolist() if _has_value(value)]
    return values[0] if values else pd.NA


def _latest_value(series: pd.Series | None) -> Any:
    if series is None:
        return pd.NA
    datetimes = _parse_datetime_series(series)
    if datetimes.notna().any():
        return datetimes.max().isoformat()
    values = [value for value in series.tolist() if _has_value(value)]
    return values[-1] if values else pd.NA


def _parse_datetime_series(series: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    except TypeError:
        return pd.to_datetime(series, errors="coerce", utc=True)


def _sorted_non_empty_unique(values: list[Any]) -> list[str]:
    normalized_pairs = {}
    for value in values:
        normalized = _normalize_text_key(value)
        if not normalized:
            continue
        normalized_pairs[normalized] = str(value)
    return [normalized_pairs[key] for key in sorted(normalized_pairs)]


def _has_value(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _find(parent: list[int], index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def _union(parent: list[int], left_index: int, right_index: int) -> None:
    left_root = _find(parent, left_index)
    right_root = _find(parent, right_index)
    if left_root == right_root:
        return
    if left_root < right_root:
        parent[right_root] = left_root
    else:
        parent[left_root] = right_root

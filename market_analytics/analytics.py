from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC

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
EXPERIENCE_YEAR_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        r"\b(?:you|your|youll|youre|du|dein|sie|ihr|vous|votre|profile|profil|requirements?|anforderungen|qualifications?|qualifikationen|bring|bringst|bringen|have|hast|haben|possess|verfugst|mitbringst|required|requires|minimum|min\.?|at\s+least|mindestens|au moins)\D{0,90}(?P<min>\d{1,2})\s*(?:-|to|bis|a)\s*(?P<max>\d{1,2})\s*(?:years?|yrs?|jahre|jahren|ans|annees)\b",
        r"\b(?:you|your|youll|youre|du|dein|sie|ihr|vous|votre|profile|profil|requirements?|anforderungen|qualifications?|qualifikationen|bring|bringst|bringen|have|hast|haben|possess|verfugst|mitbringst|required|requires|minimum|min\.?|at\s+least|mindestens|au moins)\D{0,90}(?P<min>\d{1,2})\+?\s*(?:years?|yrs?|jahre|jahren|ans|annees)\b",
        r"\b(?P<min>\d{1,2})\s*(?:-|to|bis|a)\s*(?P<max>\d{1,2})\s*(?:years?|yrs?|jahre|jahren|ans|annees)\s+(?:of\s+)?(?:professional\s+|relevant\s+)?(?:experience|erfahrung|experience)\b",
        r"\b(?P<min>\d{1,2})\+?\s*(?:years?|yrs?|jahre|jahren|ans|annees)\s+(?:of\s+)?(?:professional\s+|relevant\s+)?(?:experience|erfahrung|experience)\b",
    )
)
MAX_REASONABLE_EXPERIENCE_YEARS = 30
EXPERIENCE_CONTEXT_REJECT_PATTERN = re.compile(
    r"\b(?:company|provider|leader|manufacturer|firm|group|unternehmen|anbieter|seit|founded|history|market|"
    r"over|more\s+than|uber|ueber|based\s+on|hours?|hrs?|std|stunden|week|woche|wochen|month|months|monat|monate|days?|tage)\b",
    flags=re.IGNORECASE,
)


def calculate_overview_metrics(dataset: pd.DataFrame) -> pd.DataFrame:
    total_vacancies = int(len(dataset))
    total_companies = int(dataset["company"].dropna().nunique())
    average_vacancies_per_company = (
        len(dataset) / total_companies if total_companies else 0.0
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


def calculate_experience_requirements_summary(dataset: pd.DataFrame) -> pd.DataFrame:
    experience = _experience_requirement_frame(dataset)
    total_vacancies = int(len(dataset))
    seniority = dataset["seniority"].fillna(UNKNOWN_LABEL)
    known_seniority_count = int(seniority.ne(UNKNOWN_LABEL).sum())
    experience_count = int(len(experience))
    metrics: list[dict[str, float | int | str | None]] = [
        {"metric": "total_vacancies", "value": total_vacancies},
        {"metric": "seniority_known_count", "value": known_seniority_count},
        {
            "metric": "seniority_known_share",
            "value": round(known_seniority_count / total_vacancies, 4) if total_vacancies else 0.0,
        },
        {"metric": "experience_years_mentioned_count", "value": experience_count},
        {
            "metric": "experience_years_mentioned_share",
            "value": round(experience_count / total_vacancies, 4) if total_vacancies else 0.0,
        },
    ]
    if experience_count:
        metrics.extend(
            [
                {
                    "metric": "average_min_experience_years",
                    "value": round(float(experience["experience_min_years"].mean()), 2),
                },
                {
                    "metric": "median_min_experience_years",
                    "value": round(float(experience["experience_min_years"].median()), 2),
                },
                {
                    "metric": "average_experience_years",
                    "value": round(float(experience["experience_mid_years"].mean()), 2),
                },
                {
                    "metric": "median_experience_years",
                    "value": round(float(experience["experience_mid_years"].median()), 2),
                },
            ]
        )
    return pd.DataFrame(metrics)


def calculate_experience_by_seniority(dataset: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "seniority",
        "vacancy_count",
        "share",
        "experience_years_count",
        "average_min_experience_years",
        "median_min_experience_years",
        "average_experience_years",
        "median_experience_years",
        "rank",
    ]
    if dataset.empty:
        return pd.DataFrame(columns=columns)

    seniority_counts = (
        dataset["seniority"]
        .fillna(UNKNOWN_LABEL)
        .value_counts(dropna=False)
        .rename_axis("seniority")
        .reset_index(name="vacancy_count")
    )
    seniority_counts["share"] = (seniority_counts["vacancy_count"] / len(dataset)).round(4)
    experience = _experience_requirement_frame(dataset)
    if experience.empty:
        seniority_counts["experience_years_count"] = 0
        seniority_counts["average_min_experience_years"] = pd.NA
        seniority_counts["median_min_experience_years"] = pd.NA
        seniority_counts["average_experience_years"] = pd.NA
        seniority_counts["median_experience_years"] = pd.NA
    else:
        grouped = (
            experience.groupby("seniority", dropna=False)
            .agg(
                experience_years_count=("experience_min_years", "count"),
                average_min_experience_years=("experience_min_years", "mean"),
                median_min_experience_years=("experience_min_years", "median"),
                average_experience_years=("experience_mid_years", "mean"),
                median_experience_years=("experience_mid_years", "median"),
            )
            .reset_index()
        )
        seniority_counts = seniority_counts.merge(grouped, how="left", on="seniority")
        seniority_counts["experience_years_count"] = (
            seniority_counts["experience_years_count"].fillna(0).astype(int)
        )
        for column in (
            "average_min_experience_years",
            "median_min_experience_years",
            "average_experience_years",
            "median_experience_years",
        ):
            seniority_counts[column] = seniority_counts[column].round(2)

    seniority_counts = seniority_counts.sort_values(
        ["vacancy_count", "seniority"],
        ascending=[False, True],
    ).reset_index(drop=True)
    seniority_counts["rank"] = seniority_counts.index + 1
    return seniority_counts[columns]


def calculate_vacancy_trend_outputs(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    published = _published_vacancy_frame(dataset)
    closed = _closed_vacancy_frame(dataset)
    latest_date = _latest_available_date(published, closed)

    daily = _build_period_trend_frame(
        published=published,
        closed=closed,
        frequency="D",
        period_column="date",
    )
    weekly = _build_period_trend_frame(
        published=published,
        closed=closed,
        frequency="W-SUN",
        period_column="week_start",
    )
    monthly = _build_monthly_seasonality_frame(published)
    summary = _build_vacancy_trend_summary(
        published=published,
        closed=closed,
        latest_date=latest_date,
    )
    daily_segments = _build_segment_trend_frame(
        published=published,
        closed=closed,
        frequency="D",
        period_column="date",
    )
    weekly_segments = _build_segment_trend_frame(
        published=published,
        closed=closed,
        frequency="W-SUN",
        period_column="week_start",
    )
    return {
        "vacancy_trends_summary": summary,
        "vacancy_trends_daily": daily,
        "vacancy_trends_weekly": weekly,
        "vacancy_trends_monthly": monthly,
        "vacancy_trends_segments_daily": daily_segments,
        "vacancy_trends_segments_weekly": weekly_segments,
    }


def _published_vacancy_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    if "publication_date" not in dataset.columns:
        return pd.DataFrame(columns=["published_date", "canton", "role_category"])

    published_at = _parse_datetime_series(dataset["publication_date"])
    result = pd.DataFrame(
        {
            "published_date": published_at.dt.date,
            "canton": dataset.get("canton", UNKNOWN_LABEL),
            "role_category": dataset.get("role_category", UNKNOWN_LABEL),
        }
    )
    result["canton"] = result["canton"].fillna(UNKNOWN_LABEL)
    result["role_category"] = result["role_category"].fillna(UNKNOWN_LABEL)
    return result.dropna(subset=["published_date"]).reset_index(drop=True)


def _closed_vacancy_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    required_columns = {"last_seen_at", "publication_date"}
    if not required_columns.issubset(dataset.columns):
        return pd.DataFrame(columns=["closed_date", "canton", "role_category"])

    last_seen_at = _parse_datetime_series(dataset["last_seen_at"])
    if last_seen_at.dropna().empty:
        return pd.DataFrame(columns=["closed_date", "canton", "role_category"])

    latest_seen_date = last_seen_at.max().date()
    closed_mask = last_seen_at.dt.date < latest_seen_date
    result = pd.DataFrame(
        {
            "closed_date": last_seen_at.dt.date,
            "canton": dataset.get("canton", UNKNOWN_LABEL),
            "role_category": dataset.get("role_category", UNKNOWN_LABEL),
        }
    )
    result["canton"] = result["canton"].fillna(UNKNOWN_LABEL)
    result["role_category"] = result["role_category"].fillna(UNKNOWN_LABEL)
    return result.loc[closed_mask].dropna(subset=["closed_date"]).reset_index(drop=True)


def _latest_available_date(published: pd.DataFrame, closed: pd.DataFrame) -> pd.Timestamp | None:
    candidates: list[pd.Timestamp] = []
    if not published.empty:
        candidates.append(pd.to_datetime(published["published_date"]).max())
    if not closed.empty:
        candidates.append(pd.to_datetime(closed["closed_date"]).max())
    if not candidates:
        return None
    return max(candidates)


def _build_period_trend_frame(
    *,
    published: pd.DataFrame,
    closed: pd.DataFrame,
    frequency: str,
    period_column: str,
) -> pd.DataFrame:
    if published.empty:
        return pd.DataFrame(
            columns=[
                period_column,
                "published_count",
                "closed_count",
                "net_change",
                "growth_rate",
            ]
        )

    published_counts = _resample_date_counts(published["published_date"], frequency)
    closed_counts = (
        _resample_date_counts(closed["closed_date"], frequency)
        if not closed.empty
        else pd.Series(dtype="int64")
    )
    index = published_counts.index.union(closed_counts.index)
    if index.empty:
        return pd.DataFrame(columns=[period_column, "published_count", "closed_count", "net_change"])

    trend = pd.DataFrame(index=index.sort_values())
    trend["published_count"] = published_counts.reindex(trend.index, fill_value=0).astype(int)
    trend["closed_count"] = closed_counts.reindex(trend.index, fill_value=0).astype(int)
    trend["net_change"] = trend["published_count"] - trend["closed_count"]
    trend["growth_rate"] = (
        trend["published_count"].pct_change().replace([float("inf"), float("-inf")], pd.NA)
    ).round(4)
    trend = trend.reset_index(names=period_column)
    trend[period_column] = trend[period_column].dt.date.astype(str)
    return trend


def _build_monthly_seasonality_frame(published: pd.DataFrame) -> pd.DataFrame:
    if published.empty:
        return pd.DataFrame(columns=["month", "vacancy_count", "share"])

    months = pd.to_datetime(published["published_date"]).dt.month
    counts = months.value_counts().rename_axis("month").reset_index(name="vacancy_count")
    counts = counts.sort_values("month").reset_index(drop=True)
    counts["share"] = (counts["vacancy_count"] / len(published)).round(4)
    return counts


def _build_segment_trend_frame(
    *,
    published: pd.DataFrame,
    closed: pd.DataFrame,
    frequency: str,
    period_column: str,
) -> pd.DataFrame:
    columns = [
        period_column,
        "canton",
        "role_category",
        "published_count",
        "closed_count",
        "net_change",
    ]
    if published.empty:
        return pd.DataFrame(columns=columns)

    published_counts = _segment_date_counts(
        frame=published,
        date_column="published_date",
        frequency=frequency,
        period_column=period_column,
        value_column="published_count",
    )
    closed_counts = (
        _segment_date_counts(
            frame=closed,
            date_column="closed_date",
            frequency=frequency,
            period_column=period_column,
            value_column="closed_count",
        )
        if not closed.empty
        else pd.DataFrame(columns=[period_column, "canton", "role_category", "closed_count"])
    )
    trend = published_counts.merge(
        closed_counts,
        how="outer",
        on=[period_column, "canton", "role_category"],
    )
    trend["published_count"] = trend["published_count"].fillna(0).astype(int)
    trend["closed_count"] = trend["closed_count"].fillna(0).astype(int)
    trend["net_change"] = trend["published_count"] - trend["closed_count"]
    trend = trend.sort_values([period_column, "canton", "role_category"]).reset_index(drop=True)
    return trend[columns]


def _segment_date_counts(
    *,
    frame: pd.DataFrame,
    date_column: str,
    frequency: str,
    period_column: str,
    value_column: str,
) -> pd.DataFrame:
    period = pd.to_datetime(frame[date_column]).dt.to_period(frequency).dt.start_time.dt.date.astype(str)
    grouped = (
        frame.assign(**{period_column: period})
        .groupby([period_column, "canton", "role_category"], dropna=False)
        .size()
        .reset_index(name=value_column)
    )
    return grouped


def _build_vacancy_trend_summary(
    *,
    published: pd.DataFrame,
    closed: pd.DataFrame,
    latest_date: pd.Timestamp | None,
) -> pd.DataFrame:
    metrics: list[dict[str, float | int | str | None]] = [
        {"metric": "published_total", "value": int(len(published))},
        {"metric": "closed_total", "value": int(len(closed))},
        {
            "metric": "latest_publication_date",
            "value": latest_date.date().isoformat() if latest_date is not None else None,
        },
    ]
    if latest_date is not None:
        for days in (30, 90, 180, 365):
            current_count, previous_count, growth_rate = _period_growth(
                published["published_date"],
                latest_date=latest_date,
                days=days,
            )
            metrics.extend(
                [
                    {"metric": f"published_{days}d", "value": current_count},
                    {"metric": f"published_previous_{days}d", "value": previous_count},
                    {"metric": f"growth_{days}d", "value": growth_rate},
                ]
            )
    return pd.DataFrame(metrics)


def _period_growth(
    dates: pd.Series,
    *,
    latest_date: pd.Timestamp,
    days: int,
) -> tuple[int, int, float | None]:
    normalized_dates = pd.to_datetime(dates)
    current_start = latest_date - pd.Timedelta(days=days - 1)
    previous_start = current_start - pd.Timedelta(days=days)
    previous_end = current_start - pd.Timedelta(days=1)

    current_count = int(
        ((normalized_dates >= current_start) & (normalized_dates <= latest_date)).sum()
    )
    previous_count = int(
        ((normalized_dates >= previous_start) & (normalized_dates <= previous_end)).sum()
    )
    growth_rate = (
        round((current_count - previous_count) / previous_count, 4)
        if previous_count
        else None
    )
    return current_count, previous_count, growth_rate


def _resample_date_counts(dates: pd.Series, frequency: str) -> pd.Series:
    parsed_dates = pd.to_datetime(dates)
    if parsed_dates.empty:
        return pd.Series(dtype="int64")
    return parsed_dates.groupby(parsed_dates.dt.to_period(frequency).dt.start_time).size()


def _parse_datetime_series(values: pd.Series) -> pd.Series:
    normalized = values.astype("string").str.replace(
        r"([+-]\d{2}:\d{2}):\d{2}$",
        r"\1",
        regex=True,
    )
    return pd.to_datetime(normalized, errors="coerce", utc=True).dt.tz_convert(UTC)


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


def _experience_requirement_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, float | str]] = []
    for _, row in dataset.iterrows():
        experience = _extract_experience_years(row)
        if experience is None:
            continue
        minimum, maximum = experience
        midpoint = (minimum + maximum) / 2 if maximum is not None else minimum
        records.append(
            {
                "seniority": _known_or_unknown(row.get("seniority")),
                "role_category": _known_or_unknown(row.get("role_category")),
                "experience_min_years": minimum,
                "experience_max_years": maximum,
                "experience_mid_years": midpoint,
            }
        )
    return pd.DataFrame.from_records(
        records,
        columns=[
            "seniority",
            "role_category",
            "experience_min_years",
            "experience_max_years",
            "experience_mid_years",
        ],
    )


def _extract_experience_years(row: pd.Series) -> tuple[float, float | None] | None:
    text = " ".join(
        str(value)
        for value in (
            row.get("title"),
            row.get("description_text"),
        )
        if not pd.isna(value) and str(value).strip()
    )
    if not text:
        return None

    normalized = _normalize_search_text(text)
    matches: list[tuple[float, float | None]] = []
    for pattern in EXPERIENCE_YEAR_PATTERNS:
        for match in pattern.finditer(normalized):
            if _is_rejected_experience_context(normalized, match.start(), match.end()):
                continue
            minimum = _coerce_experience_years(match.group("min"))
            maximum = _coerce_experience_years(match.groupdict().get("max"))
            if minimum is None:
                continue
            if maximum is not None and maximum < minimum:
                maximum = minimum
            matches.append((minimum, maximum))
    if not matches:
        return None
    return min(matches, key=lambda item: item[0])


def _is_rejected_experience_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 80) : min(len(text), end + 80)]
    if EXPERIENCE_CONTEXT_REJECT_PATTERN.search(window):
        required_context = re.search(
            r"\b(?:you|your|youll|youre|du|dein|sie|ihr|vous|votre|bring|bringst|"
            r"bringen|have|hast|haben|possess|verfugst|mitbringst|required|requires|"
            r"minimum|min\.?|at\s+least|mindestens|au moins)\b",
            window,
            flags=re.IGNORECASE,
        )
        return required_context is None
    return False


def _coerce_experience_years(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0 or numeric > MAX_REASONABLE_EXPERIENCE_YEARS:
        return None
    return numeric


def _known_or_unknown(value: object) -> str:
    if value is None or pd.isna(value) or not str(value).strip():
        return UNKNOWN_LABEL
    return str(value)


def _normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    without_marks = "".join(
        character for character in normalized if unicodedata.category(character) != "Mn"
    )
    return without_marks.casefold()


def exclude_staffing_agencies(dataset: pd.DataFrame) -> pd.DataFrame:
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


def calculate_city_map_details(dataset: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "city",
        "vacancy_count",
        "share",
        "role_distribution_json",
        "company_distribution_json",
        "work_mode_distribution_json",
    ]
    if dataset.empty:
        return pd.DataFrame(columns=columns)

    city_groups = (
        dataset.assign(city=dataset["city"].fillna(UNKNOWN_LABEL))
        .groupby("city", dropna=False, sort=False)
    )
    total_vacancies = len(dataset)
    records: list[dict[str, object]] = []

    for city, city_frame in city_groups:
        vacancy_count = int(len(city_frame))
        records.append(
            {
                "city": city,
                "vacancy_count": vacancy_count,
                "share": round(vacancy_count / total_vacancies, 4) if total_vacancies else 0.0,
                "role_distribution_json": json.dumps(
                    _build_dimension_distribution_items(
                        city_frame,
                        column="role_category",
                        label_key="role_category",
                    ),
                    ensure_ascii=False,
                ),
                "company_distribution_json": json.dumps(
                    _build_dimension_distribution_items(
                        city_frame,
                        column="company",
                        label_key="company",
                    ),
                    ensure_ascii=False,
                ),
                "work_mode_distribution_json": json.dumps(
                    _build_dimension_distribution_items(
                        city_frame,
                        column="work_mode",
                        label_key="work_mode",
                    ),
                    ensure_ascii=False,
                ),
            }
        )

    return pd.DataFrame.from_records(records, columns=columns).sort_values(
        ["vacancy_count", "city"],
        ascending=[False, True],
    ).reset_index(drop=True)


def _build_dimension_distribution_items(
    dataset: pd.DataFrame,
    *,
    column: str,
    label_key: str,
) -> list[dict[str, object]]:
    counts = (
        dataset[column]
        .fillna(UNKNOWN_LABEL)
        .map(_known_or_unknown)
        .value_counts(dropna=False)
        .rename_axis(label_key)
        .reset_index(name="vacancy_count")
        .sort_values(["vacancy_count", label_key], ascending=[False, True])
        .reset_index(drop=True)
    )
    total_count = int(len(dataset))
    counts["share_within_city"] = (
        counts["vacancy_count"] / total_count if total_count else 0.0
    ).round(4)
    counts["rank"] = counts.index + 1
    return [
        {
            label_key: str(row[label_key]),
            "vacancy_count": int(row["vacancy_count"]),
            "share_within_city": float(row["share_within_city"]),
            "rank": int(row["rank"]),
        }
        for row in counts.to_dict(orient="records")
    ]


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

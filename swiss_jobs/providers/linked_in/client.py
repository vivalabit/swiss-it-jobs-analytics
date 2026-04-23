from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from swiss_jobs.core.models import ClientConfig, QuerySpec, VacancyFull
from swiss_jobs.providers.jobs_ch.extractors import html_to_text

BASE_URL = "https://www.linkedin.com"


class LinkedInHttpClient:
    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        headers: dict[str, str] | None = None,
        timeout: int = 45,
        default_max_pages: int = 1,
        env_proxy_names: Sequence[str] = (),
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.default_max_pages = default_max_pages
        self.env_proxy_names = tuple(env_proxy_names)

    def search(
        self,
        config: ClientConfig,
        queries: Sequence[QuerySpec],
    ) -> tuple[list[VacancyFull], list[str], int]:
        json_path = _resolve_json_path(config)
        if json_path:
            if not json_path.is_file():
                raise RuntimeError(f"LinkedIn JSON file does not exist: {json_path}")
            jobs, warnings = parse_vacancies_from_json(json_path, base_url=self.base_url)
            if config.show_progress:
                print(
                    f"[progress] loaded {len(jobs)} LinkedIn JSON vacancies from {json_path}",
                    file=sys.stderr,
                )
            return _dedupe_vacancies(jobs), warnings, 1

        csv_path = _resolve_csv_path(config)
        if not csv_path:
            raise RuntimeError(
                "LinkedIn import provider requires --json-path/json_path or --csv-path/csv_path"
            )
        if not csv_path.is_file():
            raise RuntimeError(f"LinkedIn CSV file does not exist: {csv_path}")

        jobs, warnings = parse_vacancies_from_csv(csv_path, base_url=self.base_url)
        if config.show_progress:
            print(
                f"[progress] loaded {len(jobs)} LinkedIn CSV vacancies from {csv_path}",
                file=sys.stderr,
            )
        return _dedupe_vacancies(jobs), warnings, 1

    def open_login_session(self, config: ClientConfig) -> None:
        raise RuntimeError("LinkedIn provider now imports CSV vacancies and does not use browser login")

    def enrich_vacancies(
        self,
        vacancies: Sequence[VacancyFull],
        *,
        detail_limit: int | None,
        detail_workers: int,
        show_progress: bool,
        **_: Any,
    ) -> tuple[int, int]:
        for vacancy in vacancies:
            vacancy.detail_schema_skipped = False
            vacancy.detail_schema_error = None
        return len(vacancies), len(vacancies)


def parse_vacancies_from_csv(path: Path, *, base_url: str = BASE_URL) -> tuple[list[VacancyFull], list[str]]:
    warnings: list[str] = []
    jobs: list[VacancyFull] = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [str(name or "").strip() for name in (reader.fieldnames or [])]
        if not fieldnames:
            return [], [f"{path}: CSV header is empty"]

        normalized_fields = {_normalize_key(name) for name in fieldnames}
        if _looks_like_search_input_csv(normalized_fields):
            warnings.append(
                f"{path}: CSV looks like search-input rows, not vacancy rows; "
                "expected columns such as title/job_title, company, url, location, description"
            )
            return [], warnings

        for row_number, raw_row in enumerate(reader, start=2):
            row = _normalize_row(raw_row)
            vacancy = _vacancy_from_csv_row(row, row_number=row_number, base_url=base_url)
            if vacancy is None:
                warnings.append(f"{path}: row {row_number} skipped; missing title/job_title")
                continue
            jobs.append(vacancy)

    return jobs, warnings


def parse_vacancies_from_json(path: Path, *, base_url: str = BASE_URL) -> tuple[list[VacancyFull], list[str]]:
    warnings: list[str] = []
    jobs: list[VacancyFull] = []
    payload = _load_json_payload(path)
    records = _extract_json_records(payload)
    if not records:
        return [], [f"{path}: JSON does not contain vacancy records"]

    for index, record in enumerate(records, start=1):
        vacancy = _vacancy_from_mapping(record, row_number=index, base_url=base_url, row_source="json")
        if vacancy is None:
            warnings.append(f"{path}: record {index} skipped; missing job_title/title")
            continue
        jobs.append(vacancy)
    return jobs, warnings


def _load_json_payload(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        records = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
        return records


def _extract_json_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "records", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
        if any(key in payload for key in ("job_title", "title", "job_posting_id", "url")):
            return [dict(payload)]
    return []


def _resolve_csv_path(config: ClientConfig) -> Path | None:
    value = getattr(config, "csv_path", None)
    if not value:
        return None
    return Path(str(value)).expanduser()


def _resolve_json_path(config: ClientConfig) -> Path | None:
    value = getattr(config, "json_path", None)
    if not value:
        return None
    return Path(str(value)).expanduser()


def _looks_like_search_input_csv(normalized_fields: set[str]) -> bool:
    search_fields = {"keyword", "location", "country", "time_range", "job_type", "experience_level"}
    vacancy_fields = {"title", "job_title", "url", "job_url", "company", "company_name", "description"}
    return bool(search_fields & normalized_fields) and not bool(vacancy_fields & normalized_fields)


def _vacancy_from_csv_row(row: Mapping[str, str], *, row_number: int, base_url: str) -> VacancyFull | None:
    return _vacancy_from_mapping(row, row_number=row_number, base_url=base_url, row_source="csv")


def _vacancy_from_mapping(
    row: Mapping[str, Any],
    *,
    row_number: int,
    base_url: str,
    row_source: str,
) -> VacancyFull | None:
    title = _first_value(row, "title", "job_title", "position", "name")
    if not title:
        return None

    url = _first_value(row, "url", "job_url", "linkedin_url", "job_link", "link")
    linkedin_id = (
        _first_value(row, "linkedin_job_id", "job_posting_id", "job_id", "id", "vacancy_id")
        or _extract_linkedin_job_id(url)
        or _stable_row_id(row, row_number=row_number)
    )
    if url and not url.startswith(("http://", "https://")):
        url = f"{base_url.rstrip('/')}/{url.lstrip('/')}"
    if not url and linkedin_id:
        url = f"{base_url.rstrip('/')}/jobs/view/{linkedin_id}/"

    company = _first_value(row, "company", "company_name", "organization", "hiring_organization")
    place = _first_value(row, "location", "job_location", "place", "city")
    publication_date = _normalize_date(
        _first_value(row, "publication_date", "posted_at", "date_posted", "job_posted_date")
    )
    employment_type = _first_value(row, "employment_type", "job_employment_type", "job_type")
    workplace = _first_value(row, "workplace", "remote", "work_mode", "workplace_type")
    seniority = _first_value(row, "seniority", "job_seniority_level", "seniority_level")
    applicants = _first_value(row, "job_num_applicants", "num_applicants")
    description_html = _first_value(row, "description_html", "job_description_formatted")
    description_text = _first_value(
        row,
        "description_text",
        "description",
        "job_description",
        "job_summary",
        "summary",
    )
    if description_html and not description_text:
        description_text = html_to_text(description_html)
    if description_text and not description_html:
        description_html = html.escape(description_text)

    raw = dict(row)
    raw[f"{row_source}RowNumber"] = row_number
    raw["linkedinJobId"] = linkedin_id
    if employment_type:
        raw["employmentType"] = employment_type
        raw["jobType"] = employment_type
    if workplace:
        raw["workplace"] = workplace
    detail_attributes: dict[str, Any] = {}
    if employment_type:
        detail_attributes["employmentTypeText"] = employment_type
    if workplace:
        detail_attributes["workplace"] = workplace
    if seniority:
        detail_attributes["seniorityLevel"] = seniority
    if applicants:
        detail_attributes["applicantCountText"] = applicants
    industries = _coerce_string_list(_value_for_keys(row, "job_industries", "industry", "industries"))
    if industries:
        detail_attributes["industries"] = industries
    if detail_attributes:
        raw["detailAttributes"] = detail_attributes

    schema = _build_schema(
        row,
        title=title,
        company=company,
        place=place,
        url=url,
        description_html=description_html,
        publication_date=publication_date,
        employment_type=employment_type,
        industries=industries,
    )

    return VacancyFull(
        id=f"linkedin:{linkedin_id}",
        title=title,
        company=company,
        place=place,
        publication_date=publication_date or None,
        initial_publication_date=publication_date or None,
        is_new=_looks_new(_first_value(row, "posted_at", "job_posted_time", "date_posted")),
        url=url,
        raw=raw,
        description_html=description_html,
        description_text=description_text,
        job_posting_schema=schema,
        detail_schema_error=None,
        detail_schema_skipped=False,
        source="linkedin.com",
    )


def _build_schema(
    row: Mapping[str, Any],
    *,
    title: str,
    company: str,
    place: str,
    url: str,
    description_html: str,
    publication_date: str,
    employment_type: str,
    industries: list[str] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": title,
        "description": description_html,
        "url": url,
    }
    if publication_date:
        schema["datePosted"] = publication_date
    if employment_type:
        schema["employmentType"] = employment_type
    industry_values = industries or _coerce_string_list(_value_for_keys(row, "industry", "industries"))
    if industry_values:
        schema["industry"] = industry_values
    if company:
        organization: dict[str, Any] = {"@type": "Organization", "name": company}
        company_url = _first_value(row, "company_url", "company_link")
        company_logo = _first_value(row, "company_logo", "company_logo_url")
        if company_url:
            organization["sameAs"] = company_url
        if company_logo:
            organization["logo"] = company_logo
        schema["hiringOrganization"] = organization
    if place:
        schema["jobLocation"] = {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": place,
                "addressCountry": _first_value(row, "country_code", "country") or "CH",
            },
        }
    salary = _value_for_keys(row, "base_salary", "salary", "salary_standards")
    if salary not in (None, "", [], {}):
        schema["baseSalary"] = salary
    return schema


def _normalize_row(row: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in row.items():
        normalized_key = _normalize_key(str(key or ""))
        if not normalized_key:
            continue
        result[normalized_key] = str(value or "").strip()
    return result


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")


def _first_value(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _value_for_keys(row, key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def _value_for_keys(row: Mapping[str, Any], *keys: str) -> Any:
    normalized_lookup = {_normalize_key(str(key)): value for key, value in row.items()}
    for key in keys:
        normalized = _normalize_key(key)
        if normalized in normalized_lookup:
            return normalized_lookup[normalized]
    return None


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,;|]", value) if part.strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _extract_linkedin_job_id(url: str) -> str:
    match = re.search(r"/jobs/view/(?:[^/?#-]+-)?(?P<id>\d+)", url or "")
    return match.group("id") if match else ""


def _stable_row_id(row: Mapping[str, str], *, row_number: int) -> str:
    parts = [row.get(key, "") for key in ("title", "company", "company_name", "location", "url")]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"csv-{row_number}-{digest}"


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})", value)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", value)
    if match:
        day, month, year = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return value.strip()


def _looks_new(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in ("new", "today", "hour", "minute", "just now"))


def _dedupe_vacancies(vacancies: Sequence[VacancyFull]) -> list[VacancyFull]:
    seen: set[str] = set()
    result: list[VacancyFull] = []
    for vacancy in vacancies:
        if vacancy.id in seen:
            continue
        seen.add(vacancy.id)
        result.append(vacancy)
    return result

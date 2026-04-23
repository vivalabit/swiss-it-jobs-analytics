from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Literal, Mapping, Sequence

from .salary import extract_salary_info

ParserMode = Literal["new", "search"]
OutputFormat = Literal["full", "brief"]


class ConfigValidationError(ValueError):
    """Raised when a parser or client config is invalid."""


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result: list[str] = []
        for item in value:
            if item is None:
                continue
            result.append(str(item))
        return result
    raise ConfigValidationError(f"Expected a string or list of strings, got {type(value)!r}")


def _coerce_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ConfigValidationError(f"Field '{field_name}' must be boolean")


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigValidationError(f"Field '{field_name}' must be an integer")
    return value


def _coerce_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigValidationError(f"Field '{field_name}' must be a number")
    return float(value)


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _looks_absolute_datetime(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.search(r"\d{4}-\d{2}-\d{2}", value))


@dataclass(slots=True)
class QuerySpec:
    term: str
    location: str
    index: int
    total: int

    @property
    def label(self) -> str:
        return (
            f"query {self.index}/{self.total} "
            f"term='{self.term}' location='{self.location}'"
        )


@dataclass(slots=True)
class FilterDecision:
    passes: bool
    role_match: bool | None = None
    seniority_match: bool | None = None
    matched_keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VacancyFull:
    id: str
    title: str = ""
    company: str = ""
    place: str = ""
    publication_date: str | None = None
    initial_publication_date: str | None = None
    is_new: bool = False
    url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    description_html: str = ""
    description_text: str = ""
    job_posting_schema: dict[str, Any] | None = None
    detail_schema_error: str | None = None
    detail_schema_skipped: bool = False
    role_match: bool | None = None
    seniority_match: bool | None = None
    keywords_matched: list[str] = field(default_factory=list)
    source: str = "jobs.ch"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def posted_at(self) -> str | None:
        if _looks_absolute_datetime(self.publication_date):
            return self.publication_date
        if _looks_absolute_datetime(self.initial_publication_date):
            return self.initial_publication_date
        return self.publication_date or self.initial_publication_date

    @property
    def employment_type(self) -> str | None:
        schema = self.job_posting_schema or {}
        raw_value = schema.get("employmentType")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()

        raw = self.raw or {}
        for key in ("employmentType", "employment_type", "jobType"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @property
    def salary_min(self) -> int | None:
        return extract_salary_info(self).minimum

    @property
    def salary_max(self) -> int | None:
        return extract_salary_info(self).maximum

    @property
    def salary_currency(self) -> str | None:
        return extract_salary_info(self).currency

    @property
    def salary_unit(self) -> str | None:
        return extract_salary_info(self).unit

    @property
    def salary_text(self) -> str | None:
        return extract_salary_info(self).text

    @property
    def salary_display(self) -> str | None:
        return extract_salary_info(self).display_text

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "place": self.place,
            "publication_date": self.publication_date,
            "initial_publication_date": self.initial_publication_date,
            "is_new": self.is_new,
            "url": self.url,
            "raw": self.raw,
            "description_html": self.description_html,
            "description_text": self.description_text,
            "job_posting_schema": self.job_posting_schema,
            "detail_schema_error": self.detail_schema_error,
            "detail_schema_skipped": self.detail_schema_skipped,
            "role_match": self.role_match,
            "seniority_match": self.seniority_match,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "salary_unit": self.salary_unit,
            "salary_text": self.salary_text,
            "keywords_matched": list(self.keywords_matched),
            "source": self.source,
        }
        data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VacancyFull":
        known_keys = {
            "id",
            "title",
            "company",
            "place",
            "publication_date",
            "initial_publication_date",
            "is_new",
            "url",
            "raw",
            "description_html",
            "description_text",
            "job_posting_schema",
            "detail_schema_error",
            "detail_schema_skipped",
            "role_match",
            "seniority_match",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_unit",
            "salary_text",
            "keywords_matched",
            "source",
        }
        payload = dict(data)
        extra = {key: value for key, value in payload.items() if key not in known_keys}
        return cls(
            id=str(payload.get("id") or ""),
            title=str(payload.get("title") or ""),
            company=str(payload.get("company") or ""),
            place=str(payload.get("place") or ""),
            publication_date=payload.get("publication_date"),
            initial_publication_date=payload.get("initial_publication_date"),
            is_new=bool(payload.get("is_new")),
            url=str(payload.get("url") or ""),
            raw=dict(payload.get("raw") or {}),
            description_html=str(payload.get("description_html") or ""),
            description_text=str(payload.get("description_text") or ""),
            job_posting_schema=payload.get("job_posting_schema"),
            detail_schema_error=payload.get("detail_schema_error"),
            detail_schema_skipped=bool(payload.get("detail_schema_skipped")),
            role_match=payload.get("role_match"),
            seniority_match=payload.get("seniority_match"),
            keywords_matched=list(payload.get("keywords_matched") or []),
            source=str(payload.get("source") or "jobs.ch"),
            extra=extra,
        )


@dataclass(slots=True)
class VacancyBrief:
    id: str
    title: str
    company: str
    location: str
    posted_at: str | None
    employment_type: str | None
    seniority_match: bool | None
    role_match: bool | None
    url: str
    summary: str | None
    salary: str | None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_unit: str | None = None
    salary_text: str | None = None
    keywords_matched: list[str] = field(default_factory=list)
    source: str = "jobs.ch"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "posted_at": self.posted_at,
            "employment_type": self.employment_type,
            "seniority_match": self.seniority_match,
            "role_match": self.role_match,
            "url": self.url,
            "summary": self.summary,
            "salary": self.salary,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "salary_unit": self.salary_unit,
            "salary_text": self.salary_text,
            "keywords_matched": list(self.keywords_matched),
            "source": self.source,
        }


@dataclass(slots=True)
class ParserStats:
    total_queries: int = 0
    successful_queries: int = 0
    total_fetched: int = 0
    after_text_filters: int = 0
    after_role_filters: int = 0
    filtered_out: int = 0
    new_jobs: int = 0
    detail_requested: bool = False
    detail_attempted: int = 0
    detail_enriched: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_queries": self.total_queries,
            "successful_queries": self.successful_queries,
            "total_fetched": self.total_fetched,
            "after_text_filters": self.after_text_filters,
            "after_role_filters": self.after_role_filters,
            "filtered_out": self.filtered_out,
            "new_jobs": self.new_jobs,
            "detail_requested": self.detail_requested,
            "detail_attempted": self.detail_attempted,
            "detail_enriched": self.detail_enriched,
        }


@dataclass(slots=True)
class ClientConfig:
    client_id: str = "default"
    name: str = ""
    mode: ParserMode = "new"
    term: str = ""
    terms: list[str] = field(default_factory=list)
    location: str = ""
    locations: list[str] = field(default_factory=list)
    canton: str | None = None
    max_pages: int = 0
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    role_keywords: list[str] = field(default_factory=list)
    seniority_keywords: list[str] = field(default_factory=list)
    require_role_and_seniority: bool = False
    skip_detail_schema: bool = False
    detail_limit: int | None = 0
    detail_workers: int = 4
    watch: int = 0
    output_format: OutputFormat = "full"
    use_state: bool = True
    use_archive: bool = True
    use_new_jobs: bool = True
    bootstrap: bool = False
    show_progress: bool = True
    json_output: bool = False
    cookies_file: str | None = None
    browser_profile_dir: str | None = None
    browser_headless: bool = True
    proxy_url: str | None = None
    proxy_file: str | None = None
    request_delay_min_seconds: float = 0.0
    request_delay_max_seconds: float = 0.0
    detail_delay_min_seconds: float = 2.0
    detail_delay_max_seconds: float = 4.0
    database_path: str | None = None
    client_config_path: str | None = None

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        source: str = "<config>",
        default_client_id: str | None = None,
    ) -> "ClientConfig":
        payload = dict(data)
        aliases = {
            "no_state": ("use_state", lambda value: not _coerce_bool(value, "no_state")),
            "no_archive": (
                "use_archive",
                lambda value: not _coerce_bool(value, "no_archive"),
            ),
            "no_new_jobs": (
                "use_new_jobs",
                lambda value: not _coerce_bool(value, "no_new_jobs"),
            ),
            "no_progress": (
                "show_progress",
                lambda value: not _coerce_bool(value, "no_progress"),
            ),
            "json": ("json_output", lambda value: _coerce_bool(value, "json")),
        }
        for legacy_key, (new_key, transform) in aliases.items():
            if legacy_key in payload:
                payload[new_key] = transform(payload.pop(legacy_key))

        allowed = {
            "client_id",
            "name",
            "mode",
            "term",
            "terms",
            "location",
            "locations",
            "canton",
            "max_pages",
            "include",
            "exclude",
            "role_keywords",
            "seniority_keywords",
            "require_role_and_seniority",
            "skip_detail_schema",
            "detail_limit",
            "detail_workers",
            "watch",
            "output_format",
            "use_state",
            "use_archive",
            "use_new_jobs",
            "bootstrap",
            "show_progress",
            "json_output",
            "cookies_file",
            "browser_profile_dir",
            "browser_headless",
            "proxy_url",
            "proxy_file",
            "request_delay_min_seconds",
            "request_delay_max_seconds",
            "detail_delay_min_seconds",
            "detail_delay_max_seconds",
            "database_path",
            "client_config_path",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ConfigValidationError(
                f"Unknown keys in config '{source}': {', '.join(unknown)}"
            )

        client_id = str(payload.get("client_id") or default_client_id or "default").strip()
        if not client_id:
            raise ConfigValidationError(f"Config '{source}' must define a non-empty client_id")

        mode = payload.get("mode", "new")
        if mode not in ("new", "search"):
            raise ConfigValidationError(f"Field 'mode' in '{source}' must be 'new' or 'search'")

        output_format = payload.get("output_format", "full")
        if output_format not in ("full", "brief"):
            raise ConfigValidationError(
                f"Field 'output_format' in '{source}' must be 'full' or 'brief'"
            )

        detail_limit = payload.get("detail_limit", 0)
        if detail_limit is not None:
            detail_limit = _coerce_int(detail_limit, "detail_limit")

        config = cls(
            client_id=client_id,
            name=str(payload.get("name") or client_id),
            mode=mode,
            term=str(payload.get("term") or ""),
            terms=_coerce_string_list(payload.get("terms")),
            location=str(payload.get("location") or ""),
            locations=_coerce_string_list(payload.get("locations")),
            canton=(
                str(payload["canton"]).strip().lower()
                if payload.get("canton") not in (None, "")
                else None
            ),
            max_pages=_coerce_int(payload.get("max_pages", 0), "max_pages"),
            include=_coerce_string_list(payload.get("include")),
            exclude=_coerce_string_list(payload.get("exclude")),
            role_keywords=_coerce_string_list(payload.get("role_keywords")),
            seniority_keywords=_coerce_string_list(payload.get("seniority_keywords")),
            require_role_and_seniority=_coerce_bool(
                payload.get("require_role_and_seniority", False),
                "require_role_and_seniority",
            ),
            skip_detail_schema=_coerce_bool(
                payload.get("skip_detail_schema", False),
                "skip_detail_schema",
            ),
            detail_limit=detail_limit,
            detail_workers=_coerce_int(payload.get("detail_workers", 4), "detail_workers"),
            watch=_coerce_int(payload.get("watch", 0), "watch"),
            output_format=output_format,
            use_state=_coerce_bool(payload.get("use_state", True), "use_state"),
            use_archive=_coerce_bool(payload.get("use_archive", True), "use_archive"),
            use_new_jobs=_coerce_bool(payload.get("use_new_jobs", True), "use_new_jobs"),
            bootstrap=_coerce_bool(payload.get("bootstrap", False), "bootstrap"),
            show_progress=_coerce_bool(
                payload.get("show_progress", True), "show_progress"
            ),
            json_output=_coerce_bool(payload.get("json_output", False), "json_output"),
            cookies_file=(
                str(Path(payload["cookies_file"]))
                if payload.get("cookies_file") not in (None, "")
                else None
            ),
            browser_profile_dir=(
                str(Path(payload["browser_profile_dir"]))
                if payload.get("browser_profile_dir") not in (None, "")
                else None
            ),
            browser_headless=_coerce_bool(
                payload.get("browser_headless", True),
                "browser_headless",
            ),
            proxy_url=(
                str(payload["proxy_url"]).strip()
                if payload.get("proxy_url") not in (None, "")
                else None
            ),
            proxy_file=(
                str(Path(payload["proxy_file"]))
                if payload.get("proxy_file") not in (None, "")
                else None
            ),
            request_delay_min_seconds=_coerce_float(
                payload.get("request_delay_min_seconds", 0.0),
                "request_delay_min_seconds",
            ),
            request_delay_max_seconds=_coerce_float(
                payload.get("request_delay_max_seconds", 0.0),
                "request_delay_max_seconds",
            ),
            detail_delay_min_seconds=_coerce_float(
                payload.get("detail_delay_min_seconds", 2.0),
                "detail_delay_min_seconds",
            ),
            detail_delay_max_seconds=_coerce_float(
                payload.get("detail_delay_max_seconds", 4.0),
                "detail_delay_max_seconds",
            ),
            database_path=(
                str(Path(payload["database_path"]))
                if payload.get("database_path") not in (None, "")
                else None
            ),
            client_config_path=(
                str(Path(payload["client_config_path"]))
                if payload.get("client_config_path") not in (None, "")
                else None
            ),
        )
        config.validate(source=source)
        return config

    def validate(self, *, source: str = "<config>") -> None:
        if self.max_pages < 0:
            raise ConfigValidationError(f"Field 'max_pages' in '{source}' must be >= 0")
        if self.watch < 0:
            raise ConfigValidationError(f"Field 'watch' in '{source}' must be >= 0")
        if self.detail_limit is not None and self.detail_limit < 0:
            raise ConfigValidationError(
                f"Field 'detail_limit' in '{source}' must be >= 0 or null"
            )
        if self.detail_workers < 1:
            raise ConfigValidationError(
                f"Field 'detail_workers' in '{source}' must be >= 1"
            )
        if self.cookies_file and not Path(self.cookies_file).is_file():
            raise ConfigValidationError(
                f"Field 'cookies_file' in '{source}' must point to an existing file"
            )
        if self.proxy_file and not Path(self.proxy_file).is_file():
            raise ConfigValidationError(
                f"Field 'proxy_file' in '{source}' must point to an existing file"
            )
        if self.request_delay_min_seconds < 0:
            raise ConfigValidationError(
                f"Field 'request_delay_min_seconds' in '{source}' must be >= 0"
            )
        if self.request_delay_max_seconds < 0:
            raise ConfigValidationError(
                f"Field 'request_delay_max_seconds' in '{source}' must be >= 0"
            )
        if self.request_delay_max_seconds < self.request_delay_min_seconds:
            raise ConfigValidationError(
                f"Field 'request_delay_max_seconds' in '{source}' must be >= request_delay_min_seconds"
            )
        if self.detail_delay_min_seconds < 0:
            raise ConfigValidationError(
                f"Field 'detail_delay_min_seconds' in '{source}' must be >= 0"
            )
        if self.detail_delay_max_seconds < 0:
            raise ConfigValidationError(
                f"Field 'detail_delay_max_seconds' in '{source}' must be >= 0"
            )
        if self.detail_delay_max_seconds < self.detail_delay_min_seconds:
            raise ConfigValidationError(
                f"Field 'detail_delay_max_seconds' in '{source}' must be >= detail_delay_min_seconds"
            )

        if self.mode == "search" and not self.effective_terms():
            raise ConfigValidationError(
                f"Config '{source}' uses mode='search' but has no term/terms"
            )

        if self.mode == "new":
            has_search_specific = any(
                [
                    self.term.strip(),
                    any(item.strip() for item in self.terms),
                    self.location.strip(),
                    any(item.strip() for item in self.locations),
                    bool(self.canton),
                ]
            )
            if has_search_specific:
                raise ConfigValidationError(
                    f"Config '{source}' uses mode='new' and must not define term/location/canton filters"
                )

    def effective_terms(self) -> list[str]:
        items = [self.term, *self.terms]
        result: list[str] = []
        for value in items:
            for chunk in str(value).split(","):
                item = chunk.strip()
                if item:
                    result.append(item)
        return _unique(result)

    def effective_locations(self) -> list[str]:
        items = [self.location, *self.locations]
        result: list[str] = []
        for value in items:
            for chunk in str(value).split(","):
                item = chunk.strip()
                if item:
                    result.append(item)
        return _unique(result)

    def build_queries(self, canton_locations: Mapping[str, Sequence[str]]) -> list[QuerySpec]:
        if self.mode == "new":
            return [QuerySpec(term="", location="", index=1, total=1)]

        terms = self.effective_terms()
        locations = self.effective_locations()
        if self.canton and not locations:
            mapped = [item.strip() for item in canton_locations.get(self.canton, []) if item.strip()]
            locations = _unique(mapped)
        if not locations:
            locations = [""]

        pairs = [(term, location) for term in terms for location in locations]
        total = len(pairs)
        return [
            QuerySpec(term=term, location=location, index=index, total=total)
            for index, (term, location) in enumerate(pairs, start=1)
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "name": self.name,
            "mode": self.mode,
            "term": self.term,
            "terms": list(self.terms),
            "location": self.location,
            "locations": list(self.locations),
            "canton": self.canton,
            "max_pages": self.max_pages,
            "include": list(self.include),
            "exclude": list(self.exclude),
            "role_keywords": list(self.role_keywords),
            "seniority_keywords": list(self.seniority_keywords),
            "require_role_and_seniority": self.require_role_and_seniority,
            "skip_detail_schema": self.skip_detail_schema,
            "detail_limit": self.detail_limit,
            "detail_workers": self.detail_workers,
            "watch": self.watch,
            "output_format": self.output_format,
            "use_state": self.use_state,
            "use_archive": self.use_archive,
            "use_new_jobs": self.use_new_jobs,
            "bootstrap": self.bootstrap,
            "show_progress": self.show_progress,
            "json_output": self.json_output,
            "cookies_file": self.cookies_file,
            "browser_profile_dir": self.browser_profile_dir,
            "browser_headless": self.browser_headless,
            "proxy_url": self.proxy_url,
            "proxy_file": self.proxy_file,
            "request_delay_min_seconds": self.request_delay_min_seconds,
            "request_delay_max_seconds": self.request_delay_max_seconds,
            "detail_delay_min_seconds": self.detail_delay_min_seconds,
            "detail_delay_max_seconds": self.detail_delay_max_seconds,
            "database_path": self.database_path,
            "client_config_path": self.client_config_path,
        }

    def with_overrides(
        self,
        override: Mapping[str, Any] | None,
        *,
        source: str = "<override>",
    ) -> "ClientConfig":
        if not override:
            return ClientConfig.from_dict(self.to_dict(), source=source)
        payload = self.to_dict()
        payload.update(dict(override))
        return ClientConfig.from_dict(payload, source=source, default_client_id=self.client_id)


@dataclass(slots=True)
class ClientRunResult:
    run_id: str
    client_id: str
    timestamp: str
    effective_config: ClientConfig
    stats: ParserStats = field(default_factory=ParserStats)
    new_jobs_full: list[VacancyFull] = field(default_factory=list)
    all_jobs_full: list[VacancyFull] = field(default_factory=list)
    output_jobs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    database_path: str | None = None

    @property
    def success(self) -> bool:
        return not self.errors

    def to_dict(
        self,
        *,
        include_jobs: bool = True,
        include_all_jobs: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "client_id": self.client_id,
            "timestamp": self.timestamp,
            "effective_config": self.effective_config.to_dict(),
            "stats": self.stats.to_dict(),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "database_path": self.database_path,
            "success": self.success,
        }
        if include_jobs:
            payload["output_jobs"] = list(self.output_jobs)
            payload["new_jobs_full"] = [job.to_dict() for job in self.new_jobs_full]
        if include_all_jobs:
            payload["all_jobs_full"] = [job.to_dict() for job in self.all_jobs_full]
        return payload

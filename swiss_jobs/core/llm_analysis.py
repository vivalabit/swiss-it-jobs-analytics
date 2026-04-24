from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import requests

from swiss_jobs.providers.jobs_ch.analytics import (
    REMOTE_MODE_KEYWORDS,
    ROLE_FAMILY_KEYWORDS,
    SENIORITY_KEYWORDS,
    SPOKEN_LANGUAGE_KEYWORDS,
)

from .archive import utc_now_iso
from .database import JobsDatabase, StoredVacancyRecord

DEFAULT_OPENAI_MODEL = "gpt-5-nano"
OPENAI_RESPONSES_API_URL = "https://api.openai.com/v1/responses"
MODEL_PRICING_USD_PER_1M_TOKENS: dict[str, dict[str, float]] = {
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
}

LIST_FIELDS = (
    "role_family_matches",
    "seniority_labels",
    "employment_types",
    "programming_languages",
    "frameworks_libraries",
    "cloud_platforms",
    "data_platforms",
    "databases",
    "platforms",
    "tools",
    "vendors",
    "protocols_standards",
    "methodologies",
    "spoken_languages",
)


class OpenAIResponsesTransport(Protocol):
    def create_response(
        self,
        payload: Mapping[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


@dataclass(slots=True)
class VacancyAnalysisCostEstimate:
    vacancy_count: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_cost_usd: float
    estimated_cost_per_vacancy_usd: float
    model: str


@dataclass(slots=True)
class VacancyAnalysisRunStats:
    processed: int = 0
    updated: int = 0
    failed: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0


class RequestsOpenAIResponsesTransport:
    def __init__(
        self,
        *,
        max_attempts: int = 5,
        initial_backoff_seconds: float = 1.0,
    ) -> None:
        self.max_attempts = max_attempts
        self.initial_backoff_seconds = initial_backoff_seconds

    def create_response(
        self,
        payload: Mapping[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = requests.post(
                    OPENAI_RESPONSES_API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=dict(payload),
                    timeout=timeout_seconds,
                )
                if _is_retryable_status_code(response.status_code):
                    raise RuntimeError(
                        "Transient OpenAI API error "
                        f"(status={response.status_code}, body={_safe_response_text(response)!r})"
                    )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise RuntimeError("OpenAI API returned a non-object response.")
                return data
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_attempts or not _is_retryable_request_exception(exc):
                    raise RuntimeError(_format_transport_error(exc)) from exc
            except RuntimeError as exc:
                last_error = exc
                if attempt >= self.max_attempts or not _is_retryable_runtime_error(exc):
                    raise

            time.sleep(self.initial_backoff_seconds * (2 ** (attempt - 1)))

        if last_error is not None:
            raise RuntimeError(str(last_error)) from last_error
        raise RuntimeError("OpenAI API request failed without an explicit error.")


class OpenAIVacancyAnalyzer:
    def __init__(
        self,
        *,
        model: str = DEFAULT_OPENAI_MODEL,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        transport: OpenAIResponsesTransport | None = None,
    ) -> None:
        self.model = model
        self.api_key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        self.timeout_seconds = timeout_seconds
        self.transport = transport or RequestsOpenAIResponsesTransport()

    def analyze_database(
        self,
        database_path: str,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        only_missing: bool = True,
        dry_run: bool = False,
    ) -> tuple[VacancyAnalysisRunStats, list[dict[str, Any]]]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")

        database = JobsDatabase(database_path)
        records = database.fetch_vacancies_for_llm(
            source=source,
            limit=limit,
            offset=offset,
            only_missing=only_missing,
        )
        stats = VacancyAnalysisRunStats()
        previews: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for record in records:
            try:
                result = self.analyze_record(record)
            except Exception as exc:
                stats.failed += 1
                failures.append(
                    {
                        "vacancy_id": record.vacancy.id,
                        "source": record.vacancy.source,
                        "title": record.vacancy.title,
                        "company": record.vacancy.company,
                        "error": str(exc),
                    }
                )
                continue

            stats.processed += 1
            stats.input_tokens += result["usage"]["input_tokens"]
            stats.output_tokens += result["usage"]["output_tokens"]
            stats.total_cost_usd += result["usage"]["estimated_cost_usd"]

            previews.append(
                {
                    "vacancy_id": record.vacancy.id,
                    "source": record.vacancy.source,
                    "title": record.vacancy.title,
                    "company": record.vacancy.company,
                    "analysis": result["analysis"],
                    "usage": result["usage"],
                }
            )
            if dry_run:
                continue

            database.save_llm_analysis(
                record.vacancy.id,
                llm_analysis=result["analysis"],
                model=self.model,
                analyzed_at=utc_now_iso(),
            )
            stats.updated += 1

        if failures:
            previews.append({"failures": failures})
        return stats, previews

    def analyze_record(self, record: StoredVacancyRecord) -> dict[str, Any]:
        payload = self._build_request_payload(record)
        response = self.transport.create_response(
            payload,
            api_key=self.api_key,
            timeout_seconds=self.timeout_seconds,
        )
        text = _extract_response_text(response)
        try:
            raw_analysis = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"OpenAI returned invalid JSON for vacancy '{record.vacancy.id}': {text!r}"
            ) from exc
        if not isinstance(raw_analysis, dict):
            raise RuntimeError(
                f"OpenAI returned non-object JSON for vacancy '{record.vacancy.id}'."
            )

        analysis = normalize_llm_analysis(raw_analysis)
        input_tokens, output_tokens = _extract_usage_tokens(response)
        estimated_cost = estimate_token_cost_usd(
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return {
            "analysis": analysis,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": round(estimated_cost, 6),
            },
        }

    def estimate_cost(
        self,
        database_path: str,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        only_missing: bool = False,
        estimated_output_tokens_per_vacancy: int = 280,
    ) -> VacancyAnalysisCostEstimate:
        database = JobsDatabase(database_path)
        records = database.fetch_vacancies_for_llm(
            source=source,
            limit=limit,
            offset=offset,
            only_missing=only_missing,
        )
        estimated_input_tokens = sum(
            estimate_input_tokens_for_record(record, model=self.model)
            for record in records
        )
        estimated_output_tokens = estimated_output_tokens_per_vacancy * len(records)
        estimated_total_cost_usd = estimate_token_cost_usd(
            model=self.model,
            input_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens,
        )
        vacancy_count = len(records)
        return VacancyAnalysisCostEstimate(
            vacancy_count=vacancy_count,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_total_cost_usd=round(estimated_total_cost_usd, 4),
            estimated_cost_per_vacancy_usd=round(
                estimated_total_cost_usd / vacancy_count, 6
            )
            if vacancy_count
            else 0.0,
            model=self.model,
        )

    def _build_request_payload(self, record: StoredVacancyRecord) -> dict[str, Any]:
        return {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": "minimal"},
            "max_output_tokens": 600,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "vacancy_analysis",
                    "strict": True,
                    "schema": build_analysis_json_schema(),
                }
            },
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": build_system_instructions(),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": build_user_payload(record),
                        }
                    ],
                },
            ],
        }


def build_system_instructions() -> str:
    role_values = ", ".join(sorted(ROLE_FAMILY_KEYWORDS))
    seniority_values = ", ".join(sorted(SENIORITY_KEYWORDS))
    work_mode_values = ", ".join(sorted(REMOTE_MODE_KEYWORDS))
    language_values = ", ".join(sorted(SPOKEN_LANGUAGE_KEYWORDS))
    return (
        "You normalize Swiss IT job vacancies for analytics. Return valid JSON only. "
        "Use all vacancy information provided, including title, place, description, raw metadata, "
        "job schema, and existing rule-based analytics as hints. "
        "You may infer only high-confidence categorical fields: skills, role family, seniority, "
        "work mode, and location normalization. "
        "Do not invent salary numbers, years of experience, exact location, or technologies that "
        "are not supported by the vacancy text or metadata. "
        "When a field is unknown, return null for singular fields and [] for list fields. "
        f"Allowed role_family_primary values: {role_values}. "
        f"Allowed seniority_labels values: {seniority_values}. "
        f"Allowed remote_mode values: {work_mode_values}. "
        f"Allowed spoken_languages values: {language_values}. "
        "For job_location.region use a Swiss canton code like ZH, BE, VD when explicit or clearly "
        "derivable from the vacancy city/place; otherwise return null."
    )


def build_user_payload(record: StoredVacancyRecord) -> str:
    vacancy = record.vacancy
    payload = {
        "vacancy": {
            "id": vacancy.id,
            "source": vacancy.source,
            "title": vacancy.title,
            "company": vacancy.company,
            "place": vacancy.place,
            "publication_date": vacancy.publication_date,
            "employment_type": vacancy.employment_type,
            "description_text": _trim_text(vacancy.description_text, limit=12000),
            "job_posting_schema": _prune_for_prompt(vacancy.job_posting_schema),
            "raw": _prune_for_prompt(vacancy.raw),
        },
        "existing_analytics": _prune_for_prompt(record.analytics),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_analysis_json_schema() -> dict[str, Any]:
    role_values = sorted(ROLE_FAMILY_KEYWORDS)
    seniority_values = sorted(SENIORITY_KEYWORDS)
    work_mode_values = sorted(REMOTE_MODE_KEYWORDS)
    language_values = sorted(SPOKEN_LANGUAGE_KEYWORDS)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "normalized_title": _nullable_schema({"type": "string", "maxLength": 160}),
            "role_family_primary": _nullable_schema(
                {"type": "string", "enum": role_values}
            ),
            "role_family_matches": {
                "type": "array",
                "items": {"type": "string", "enum": role_values},
            },
            "seniority_labels": {
                "type": "array",
                "items": {"type": "string", "enum": seniority_values},
            },
            "remote_mode": _nullable_schema(
                {"type": "string", "enum": work_mode_values}
            ),
            "job_location": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "locality": _nullable_schema({"type": "string", "maxLength": 120}),
                    "region": _nullable_schema({"type": "string", "maxLength": 16}),
                    "country": _nullable_schema({"type": "string", "maxLength": 16}),
                },
                "required": ["locality", "region", "country"],
            },
            "employment_types": {"type": "array", "items": {"type": "string"}},
            "programming_languages": {"type": "array", "items": {"type": "string"}},
            "frameworks_libraries": {"type": "array", "items": {"type": "string"}},
            "cloud_platforms": {"type": "array", "items": {"type": "string"}},
            "data_platforms": {"type": "array", "items": {"type": "string"}},
            "databases": {"type": "array", "items": {"type": "string"}},
            "platforms": {"type": "array", "items": {"type": "string"}},
            "tools": {"type": "array", "items": {"type": "string"}},
            "vendors": {"type": "array", "items": {"type": "string"}},
            "protocols_standards": {"type": "array", "items": {"type": "string"}},
            "methodologies": {"type": "array", "items": {"type": "string"}},
            "spoken_languages": {
                "type": "array",
                "items": {"type": "string", "enum": language_values},
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "confidence_reasons": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "normalized_title",
            "role_family_primary",
            "role_family_matches",
            "seniority_labels",
            "remote_mode",
            "job_location",
            "employment_types",
            "programming_languages",
            "frameworks_libraries",
            "cloud_platforms",
            "data_platforms",
            "databases",
            "platforms",
            "tools",
            "vendors",
            "protocols_standards",
            "methodologies",
            "spoken_languages",
            "confidence",
            "confidence_reasons",
        ],
    }


def normalize_llm_analysis(payload: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    normalized_title = _normalize_nullable_string(payload.get("normalized_title"))
    if normalized_title:
        result["normalized_title"] = normalized_title

    role_family_primary = _normalize_nullable_enum(
        payload.get("role_family_primary"),
        allowed=ROLE_FAMILY_KEYWORDS,
    )
    if role_family_primary:
        result["role_family_primary"] = role_family_primary

    role_matches = _normalize_enum_list(
        payload.get("role_family_matches"),
        allowed=ROLE_FAMILY_KEYWORDS,
    )
    if role_matches:
        result["role_family_matches"] = role_matches

    seniority_labels = _normalize_enum_list(
        payload.get("seniority_labels"),
        allowed=SENIORITY_KEYWORDS,
    )
    if seniority_labels:
        result["seniority_labels"] = seniority_labels

    remote_mode = _normalize_nullable_enum(
        payload.get("remote_mode"),
        allowed=REMOTE_MODE_KEYWORDS,
    )
    if remote_mode:
        result["remote_mode"] = remote_mode

    job_location = _normalize_job_location(payload.get("job_location"))
    if job_location:
        result["job_location"] = job_location

    for field_name in LIST_FIELDS:
        if field_name == "role_family_matches" or field_name == "seniority_labels":
            continue
        if field_name == "spoken_languages":
            values = _normalize_enum_list(
                payload.get(field_name),
                allowed=SPOKEN_LANGUAGE_KEYWORDS,
            )
        else:
            values = _normalize_string_list(payload.get(field_name))
        if values:
            result[field_name] = values

    confidence = _normalize_nullable_enum(
        payload.get("confidence"),
        allowed={"low": (), "medium": (), "high": ()},
    )
    if confidence:
        result["confidence"] = confidence
    confidence_reasons = _normalize_string_list(payload.get("confidence_reasons"))
    if confidence_reasons:
        result["confidence_reasons"] = confidence_reasons
    return result


def estimate_input_tokens_for_record(record: StoredVacancyRecord, *, model: str) -> int:
    system_text = build_system_instructions()
    user_text = build_user_payload(record)
    schema_text = json.dumps(build_analysis_json_schema(), ensure_ascii=False, sort_keys=True)
    _ = model
    return estimate_tokens_from_text(system_text + user_text + schema_text)


def estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def estimate_token_cost_usd(*, model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING_USD_PER_1M_TOKENS.get(model)
    if pricing is None:
        raise ValueError(f"Unsupported pricing model: {model}")
    return (
        input_tokens / 1_000_000 * pricing["input"]
        + output_tokens / 1_000_000 * pricing["output"]
    )


def _extract_usage_tokens(response: Mapping[str, Any]) -> tuple[int, int]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    return input_tokens, output_tokens


def _extract_response_text(response: Mapping[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = response.get("output")
    if not isinstance(output, list):
        raise RuntimeError("OpenAI response does not contain output text.")

    parts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        for content_item in item.get("content", []) or []:
            if not isinstance(content_item, Mapping):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    if not parts:
        raise RuntimeError("OpenAI response does not contain message text.")
    return "\n".join(parts)


def _safe_response_text(response: requests.Response) -> str:
    try:
        text = response.text
    except Exception:
        return ""
    return text[:1000]


def _is_retryable_status_code(status_code: int) -> bool:
    return status_code in {408, 409, 429, 500, 502, 503, 504, 520, 522, 524}


def _is_retryable_request_exception(exc: requests.RequestException) -> bool:
    response = getattr(exc, "response", None)
    if response is not None and isinstance(response, requests.Response):
        return _is_retryable_status_code(response.status_code)
    return True


def _is_retryable_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return "transient openai api error" in message


def _format_transport_error(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    if response is not None and isinstance(response, requests.Response):
        return (
            "OpenAI API request failed "
            f"(status={response.status_code}, body={_safe_response_text(response)!r})"
        )
    return f"OpenAI API request failed: {exc}"


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = " ".join(item.strip().lower().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_enum_list(value: Any, *, allowed: Mapping[str, Any]) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _normalize_nullable_enum(item, allowed=allowed)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_nullable_enum(value: Any, *, allowed: Mapping[str, Any]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return normalized if normalized in allowed else None


def _normalize_nullable_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().split())
    return normalized or None


def _normalize_job_location(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    locality = _normalize_nullable_string(value.get("locality"))
    region = _normalize_nullable_string(value.get("region"))
    country = _normalize_nullable_string(value.get("country"))
    if region:
        region = region.upper()
    if country and len(country) <= 3:
        country = country.upper()
    result = {
        key: item
        for key, item in {
            "locality": locality,
            "region": region,
            "country": country,
        }.items()
        if item
    }
    return result


def _nullable_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _trim_text(value: str, *, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _prune_for_prompt(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in {"description_html", "html", "body_html"}:
                continue
            cleaned = _prune_for_prompt(item)
            if cleaned in (None, "", [], {}):
                continue
            result[str(key)] = cleaned
        return result
    if isinstance(value, list):
        items = [_prune_for_prompt(item) for item in value]
        return [item for item in items if item not in (None, "", [], {})][:50]
    if isinstance(value, str):
        return _trim_text(" ".join(value.split()), limit=600)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _trim_text(str(value), limit=600)

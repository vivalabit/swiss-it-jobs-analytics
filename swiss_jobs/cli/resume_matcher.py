from __future__ import annotations

import base64
import html
import ipaddress
import io
import json
import os
import re
import sqlite3
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse

import requests

from swiss_jobs.core.llm_analysis import RequestsOpenAIResponsesTransport
from swiss_jobs.core.locations import normalize_location_display

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RESUME_MATCH_TERM_KEYS = (
    "programming_languages",
    "frameworks_libraries",
    "cloud_platforms",
    "databases",
    "tools",
    "methodologies",
    "methodology",
    "vendors",
    "platforms",
    "role_family_primary",
    "role_family",
    "remote_mode",
    "seniority_labels",
)

RESUME_MATCH_STOPWORDS = {
    "about",
    "also",
    "and",
    "are",
    "auf",
    "avec",
    "bei",
    "can",
    "das",
    "der",
    "die",
    "ein",
    "eine",
    "for",
    "from",
    "have",
    "ist",
    "mit",
    "not",
    "oder",
    "our",
    "per",
    "the",
    "und",
    "une",
    "von",
    "with",
    "you",
    "your",
    "zur",
    "zum",
    "experience",
    "knowledge",
    "looking",
    "need",
    "skills",
    "team",
    "required",
    "requirements",
    "role",
    "we",
    "will",
    "work",
    "working",
}
VACANCY_FETCH_MAX_BYTES = 2_000_000
VACANCY_FETCH_TIMEOUT = (5, 15)
VACANCY_FETCH_USER_AGENT = (
    "Mozilla/5.0 (compatible; SwissITJobsResumeMatcher/1.0; +https://localhost)"
)

def _connect_readonly(database_path: Path) -> sqlite3.Connection:
    uri = database_path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection

def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _strip_dotenv_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value.split(" #", 1)[0].strip()


def _project_dotenv_value(key: str) -> str:
    dotenv_path = PROJECT_ROOT / ".env"
    if not dotenv_path.is_file():
        return ""
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        raw_key, raw_value = line.split("=", 1)
        if raw_key.strip() == key:
            return _strip_dotenv_value(raw_value.strip())
    return ""


def _openai_api_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or _project_dotenv_value("OPENAI_API_KEY")).strip()

def _load_json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}

def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        clean = value.strip()
        return [clean] if clean else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_listify(item))
        return result
    return [str(value)]

def _normalized_url_candidates(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []

    candidates = {text, text.rstrip("/")}
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            path=parsed.path.rstrip("/") or parsed.path,
            fragment="",
        )
        candidates.add(urlunparse(normalized))
        candidates.add(urlunparse(normalized._replace(query="")))
    return sorted(candidate for candidate in candidates if candidate)


def _resume_text_terms(text: str, *, limit: int = 18) -> list[str]:
    counts: dict[str, int] = {}
    for raw_word in re.findall(r"[\w.+#-]+", text, flags=re.UNICODE):
        word = raw_word.strip("._-").lower()
        if len(word) < 2 or word.isdigit() or word in RESUME_MATCH_STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [
        term
        for term, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _resume_terms_from_analytics(analytics: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in RESUME_MATCH_TERM_KEYS:
        terms.extend(_listify(analytics.get(key)))
    return terms


def _dedupe_terms(values: Iterable[Any], *, limit: int = 24) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        term = str(value or "").strip()
        if not term:
            continue
        normalized = term.lower()
        if normalized in seen or normalized in RESUME_MATCH_STOPWORDS:
            continue
        seen.add(normalized)
        terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def _clamp_score(value: Any) -> int:
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def _normalize_short_text_list(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text[:220])
        if len(result) >= limit:
            break
    return result


def _normalize_resume_gap_items(value: Any, *, limit: int = 8) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        requirement = " ".join(str(item.get("requirement") or "").strip().split())
        resume_gap = " ".join(str(item.get("resume_gap") or "").strip().split())
        recommended_change = " ".join(str(item.get("recommended_change") or "").strip().split())
        if not requirement and not resume_gap and not recommended_change:
            continue
        result.append(
            {
                "requirement": requirement[:160],
                "resume_gap": resume_gap[:260],
                "recommended_change": recommended_change[:300],
            }
        )
        if len(result) >= limit:
            break
    return result


def _normalize_gap_analysis(
    payload: dict[str, Any],
    *,
    gaps: list[dict[str, str]],
    strengths: list[str],
    missing_keywords: list[str],
) -> dict[str, list[str]]:
    raw = payload.get("gap_analysis")
    blockers: list[str] = []
    strong_points: list[str] = []
    if isinstance(raw, dict):
        blockers = _normalize_short_text_list(raw.get("blockers"), limit=8)
        strong_points = _normalize_short_text_list(raw.get("strengths"), limit=8)
    if not blockers:
        blockers = _normalize_short_text_list(
            [
                item.get("resume_gap") or item.get("requirement") or ""
                for item in gaps
            ],
            limit=8,
        )
    if not blockers:
        blockers = _normalize_short_text_list(missing_keywords, limit=8)
    if not strong_points:
        strong_points = _normalize_short_text_list(strengths, limit=8)
    return {"blockers": blockers, "strengths": strong_points}


def _normalize_ats_check(value: Any, *, fallback_score: int, fallback_finding: str) -> dict[str, Any]:
    if isinstance(value, dict):
        score = _clamp_score(value.get("score"))
        status = str(value.get("status") or "").strip().lower()
        finding = " ".join(str(value.get("finding") or "").strip().split())
    else:
        score = fallback_score
        status = ""
        finding = ""
    if status not in {"pass", "warning", "fail"}:
        if score >= 80:
            status = "pass"
        elif score >= 55:
            status = "warning"
        else:
            status = "fail"
    if not finding:
        finding = fallback_finding
    return {"score": score, "status": status, "finding": finding[:220]}


def _normalize_ats_compatibility(payload: dict[str, Any], *, keyword_score: int, overall_score: int) -> dict[str, Any]:
    raw = payload.get("ats_compatibility")
    raw = raw if isinstance(raw, dict) else {}
    probability = _clamp_score(raw.get("pass_probability"))
    if not probability:
        probability = round((keyword_score * 0.45) + (overall_score * 0.35) + 14)
        probability = max(0, min(100, probability))
    checks = raw.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    return {
        "pass_probability": probability,
        "checks": {
            "keywords": _normalize_ats_check(
                checks.get("keywords"),
                fallback_score=keyword_score,
                fallback_finding="Important vacancy keywords are partially covered.",
            ),
            "structure": _normalize_ats_check(
                checks.get("structure"),
                fallback_score=overall_score,
                fallback_finding="Resume structure needs clear sections and standard headings.",
            ),
            "readability": _normalize_ats_check(
                checks.get("readability"),
                fallback_score=overall_score,
                fallback_finding="Resume text should stay concise, specific, and easy to scan.",
            ),
            "format": _normalize_ats_check(
                checks.get("format"),
                fallback_score=overall_score,
                fallback_finding="Use a simple ATS-readable format without complex layout.",
            ),
        },
    }


def _resume_match_json_schema() -> dict[str, Any]:
    score_schema = {"type": "integer", "minimum": 0, "maximum": 100}
    text_array_schema = {
        "type": "array",
        "items": {"type": "string", "maxLength": 220},
        "maxItems": 12,
    }
    ats_check_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "score": score_schema,
            "status": {"type": "string", "enum": ["pass", "warning", "fail"]},
            "finding": {"type": "string", "maxLength": 220},
        },
        "required": ["score", "status", "finding"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "overall_score": score_schema,
            "skills_score": score_schema,
            "experience_score": score_schema,
            "keywords_score": score_schema,
            "matched_keywords": text_array_schema,
            "missing_keywords": text_array_schema,
            "key_strengths": text_array_schema,
            "critical_gaps": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "requirement": {"type": "string", "maxLength": 160},
                        "resume_gap": {"type": "string", "maxLength": 260},
                        "recommended_change": {"type": "string", "maxLength": 300},
                    },
                    "required": ["requirement", "resume_gap", "recommended_change"],
                },
            },
            "recommendations": {
                "type": "array",
                "items": {"type": "string", "maxLength": 320},
                "maxItems": 6,
            },
            "tailored_resume": {"type": "string", "maxLength": 12000},
            "gap_analysis": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "blockers": text_array_schema,
                    "strengths": text_array_schema,
                },
                "required": ["blockers", "strengths"],
            },
            "ats_compatibility": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pass_probability": score_schema,
                    "checks": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "keywords": ats_check_schema,
                            "structure": ats_check_schema,
                            "readability": ats_check_schema,
                            "format": ats_check_schema,
                        },
                        "required": ["keywords", "structure", "readability", "format"],
                    },
                },
                "required": ["pass_probability", "checks"],
            },
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "confidence_reason": {"type": "string", "maxLength": 320},
        },
        "required": [
            "overall_score",
            "skills_score",
            "experience_score",
            "keywords_score",
            "matched_keywords",
            "missing_keywords",
            "key_strengths",
            "critical_gaps",
            "recommendations",
            "tailored_resume",
            "gap_analysis",
            "ats_compatibility",
            "confidence",
            "confidence_reason",
        ],
    }


def _resume_match_system_prompt() -> str:
    return (
        "You are an expert Swiss IT recruiter and ATS resume reviewer. "
        "Evaluate how well the candidate resume matches the vacancy. "
        "Base every score on explicit evidence in the vacancy and resume. "
        "Do not reward unsupported claims, generic filler, or keyword stuffing. "
        "Score strictly: 90-100 means near-perfect direct match, 70-89 strong match with small gaps, "
        "50-69 partial match, 30-49 weak match, below 30 poor match. "
        "Skills score should measure required technologies, tools, domains, languages, and methods. "
        "Experience score should measure seniority, role scope, responsibilities, impact, leadership, "
        "industry/domain fit, and evidence quality. "
        "Keywords score should measure ATS wording coverage for important vacancy terms, excluding generic words. "
        "For gap_analysis.blockers, list the concrete missing evidence that can prevent screening, "
        "such as missing Docker, AWS, English B2+, required certifications, seniority, domain, or work-permit signals. "
        "For gap_analysis.strengths, list concrete resume evidence that is already a strong fit for this vacancy. "
        "For ats_compatibility, estimate ATS pass probability from keyword coverage, structure, readability, and format. "
        "Check whether the resume uses vacancy keywords, standard sections, readable wording, and ATS-friendly formatting. "
        "Return concise, actionable recommendations that tell the candidate exactly what to change. "
        "Tailor the resume draft truthfully; never invent employers, degrees, years, metrics, or projects. "
        "If information is missing, use bracketed placeholders such as [add metric] instead of inventing facts."
    )


def _resume_match_user_payload(
    *,
    vacancy_title: str,
    company: str,
    vacancy_source: dict[str, Any],
    vacancy_text: str,
    resume_text: str,
    analytics: dict[str, Any],
) -> str:
    payload = {
        "vacancy": {
            "title": vacancy_title,
            "company": company,
            "source": vacancy_source.get("source") or "",
            "location": vacancy_source.get("location") or "",
            "url": vacancy_source.get("url") or "",
            "description_text": vacancy_text[:12000],
            "analytics_hints": analytics,
        },
        "candidate_resume": resume_text[:18000],
        "task": {
            "goal": "score match quality and produce a truthful vacancy-tailored resume draft",
            "audience": "Swiss IT recruiter and ATS screening",
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _extract_openai_response_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    output = response.get("output")
    if not isinstance(output, list):
        raise ValueError("OpenAI response does not contain output text.")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        for content_item in item.get("content", []) or []:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    if not parts:
        raise ValueError("OpenAI response does not contain message text.")
    return "\n".join(parts)


def _normalize_llm_resume_match(payload: dict[str, Any], *, resume_text: str) -> dict[str, Any]:
    recommendations = _normalize_short_text_list(payload.get("recommendations"), limit=6)
    gaps = _normalize_resume_gap_items(payload.get("critical_gaps"))
    overall_score = _clamp_score(payload.get("overall_score"))
    skills_score = _clamp_score(payload.get("skills_score"))
    experience_score = _clamp_score(payload.get("experience_score"))
    keywords_score = _clamp_score(payload.get("keywords_score"))
    matched_keywords = _normalize_short_text_list(payload.get("matched_keywords"), limit=12)
    missing_keywords = _normalize_short_text_list(payload.get("missing_keywords"), limit=12)
    key_strengths = _normalize_short_text_list(payload.get("key_strengths"), limit=12)
    if not recommendations:
        recommendations = [
            item["recommended_change"]
            for item in gaps
            if item.get("recommended_change")
        ][:6]
    gap_analysis = _normalize_gap_analysis(
        payload,
        gaps=gaps,
        strengths=key_strengths,
        missing_keywords=missing_keywords,
    )
    ats_compatibility = _normalize_ats_compatibility(
        payload,
        keyword_score=keywords_score,
        overall_score=overall_score,
    )
    tailored_resume = str(payload.get("tailored_resume") or "").strip()
    if not tailored_resume:
        tailored_resume = resume_text
    return {
        "score": overall_score,
        "score_breakdown": {
            "skills": skills_score,
            "experience": experience_score,
            "keywords": keywords_score,
        },
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "key_strengths": key_strengths,
        "critical_gaps": gaps,
        "gap_analysis": gap_analysis,
        "ats_compatibility": ats_compatibility,
        "recommendations": recommendations,
        "tailored_resume": tailored_resume,
        "confidence": str(payload.get("confidence") or "").strip(),
        "confidence_reason": str(payload.get("confidence_reason") or "").strip(),
    }


def build_llm_resume_match(
    *,
    model: str,
    vacancy_title: str,
    company: str,
    vacancy_source: dict[str, Any],
    vacancy_text: str,
    analytics: dict[str, Any],
    resume_text: str,
    api_key: str | None = None,
    transport: Any | None = None,
) -> dict[str, Any]:
    clean_model = _clean_text(model) or "gpt-5.5"
    clean_api_key = (api_key or _openai_api_key()).strip()
    if not clean_api_key:
        raise ValueError("OPENAI_API_KEY is not set. Save it in Settings before running resume match.")
    client = transport or RequestsOpenAIResponsesTransport()
    response = client.create_response(
        {
            "model": clean_model,
            "store": False,
            "reasoning": {"effort": "medium"},
            "max_output_tokens": 3600,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "resume_match_analysis",
                    "strict": True,
                    "schema": _resume_match_json_schema(),
                }
            },
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": _resume_match_system_prompt()}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _resume_match_user_payload(
                                vacancy_title=vacancy_title,
                                company=company,
                                vacancy_source=vacancy_source,
                                vacancy_text=vacancy_text,
                                analytics=analytics,
                                resume_text=resume_text,
                            ),
                        }
                    ],
                },
            ],
        },
        api_key=clean_api_key,
        timeout_seconds=90.0,
    )
    text = _extract_openai_response_text(response)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI returned invalid resume match JSON: {text[:500]!r}") from exc
    if not isinstance(payload, dict):
        raise ValueError("OpenAI returned non-object resume match JSON.")
    result = _normalize_llm_resume_match(payload, resume_text=resume_text)
    result["model"] = clean_model
    return result


def _resume_vacancy_from_row(database_path: Path, row: sqlite3.Row) -> dict[str, Any]:
    analytics = _load_json_object(row["analytics_json"])
    return {
        "database": str(database_path),
        "id": row["vacancy_id"],
        "source": row["source"] or "",
        "title": row["title"] or "",
        "company": row["company"] or "",
        "location": normalize_location_display(row["place"]) or row["place"] or "",
        "url": row["url"] or "",
        "description_text": str(row["description_text"] or "").strip(),
        "analytics": analytics,
    }


def _find_resume_vacancy(database_paths: Iterable[Path], vacancy_url: str) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    candidates = _normalized_url_candidates(vacancy_url)
    if not candidates:
        return None, []

    placeholders = ", ".join("?" for _ in candidates)
    query = f"""
        SELECT
            v.vacancy_id,
            v.source,
            v.title,
            v.company,
            v.place,
            v.url,
            v.description_text,
            v.analytics_json
        FROM vacancies v
        WHERE v.url IN ({placeholders})
           OR rtrim(v.url, '/') IN ({placeholders})
        ORDER BY v.last_seen_at DESC, v.vacancy_id ASC
        LIMIT 1
    """
    values = [*candidates, *[candidate.rstrip("/") for candidate in candidates]]
    database_errors: list[dict[str, str]] = []

    for database_path in database_paths:
        try:
            connection = _connect_readonly(database_path)
            try:
                row = connection.execute(query, values).fetchone()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            database_errors.append({"database": str(database_path), "error": str(exc)})
            continue
        if row:
            return _resume_vacancy_from_row(database_path, row), database_errors
    return None, database_errors


def _find_resume_vacancy_by_id(
    database_paths: Iterable[Path],
    vacancy_database: str,
    vacancy_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    clean_id = _clean_text(vacancy_id)
    clean_database = _clean_text(vacancy_database)
    if not clean_id:
        return None, []

    query = """
        SELECT
            v.vacancy_id,
            v.source,
            v.title,
            v.company,
            v.place,
            v.url,
            v.description_text,
            v.analytics_json
        FROM vacancies v
        WHERE v.vacancy_id = ?
        LIMIT 1
    """
    database_errors: list[dict[str, str]] = []

    for database_path in database_paths:
        if clean_database and str(database_path) != clean_database:
            continue
        try:
            connection = _connect_readonly(database_path)
            try:
                row = connection.execute(query, [clean_id]).fetchone()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            database_errors.append({"database": str(database_path), "error": str(exc)})
            continue
        if row:
            return _resume_vacancy_from_row(database_path, row), database_errors
    return None, database_errors


class _VacancyHtmlTextParser(HTMLParser):
    _skip_tags = {"script", "style", "noscript", "svg", "canvas", "template"}
    _block_tags = {
        "article",
        "br",
        "dd",
        "div",
        "dt",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "p",
        "section",
        "td",
        "th",
        "tr",
        "ul",
        "ol",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self.meta_title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._skip_tags:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            data = {str(key).lower(): str(value or "").strip() for key, value in attrs}
            key = data.get("property") or data.get("name")
            if key in {"og:title", "twitter:title", "title"} and data.get("content"):
                self.meta_title = data["content"]
        if tag in self._block_tags:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._skip_tags and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag in self._block_tags:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
        self._parts.append(text)

    @property
    def title(self) -> str:
        return self.meta_title or " ".join(self._title_parts).strip()

    @property
    def text(self) -> str:
        raw = " ".join(self._parts)
        raw = re.sub(r"\s*\n\s*", "\n", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        lines = []
        seen: set[str] = set()
        for line in raw.splitlines():
            clean = line.strip()
            if len(clean) < 2:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(clean)
        return "\n".join(lines)


def _is_disallowed_fetch_host(hostname: str) -> bool:
    clean = hostname.strip().strip("[]").lower()
    if clean in {"localhost", "0.0.0.0"} or clean.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(clean)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local or address.is_multicast


def _extract_external_vacancy_text(content: bytes, content_type: str, encoding: str = "") -> tuple[str, str]:
    charset = encoding or "utf-8"
    html_text = content.decode(charset, errors="replace")
    if "html" not in content_type.lower():
        text = re.sub(r"\r\n?", "\n", html_text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return "", text

    parser = _VacancyHtmlTextParser()
    parser.feed(html_text)
    parser.close()
    return parser.title.strip(), parser.text.strip()


def fetch_external_vacancy(vacancy_url: str) -> dict[str, Any] | None:
    text = _clean_text(vacancy_url)
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("vacancy URL must be an http or https URL")
    if parsed.hostname and _is_disallowed_fetch_host(parsed.hostname):
        raise ValueError("refusing to fetch private or local network vacancy URL")

    try:
        response = requests.get(
            text,
            headers={
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
                "User-Agent": VACANCY_FETCH_USER_AGENT,
            },
            timeout=VACANCY_FETCH_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"could not fetch vacancy URL: {exc}") from exc

    try:
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=32768):
            if not chunk:
                continue
            size += len(chunk)
            if size > VACANCY_FETCH_MAX_BYTES:
                raise ValueError("vacancy page is too large to read automatically")
            chunks.append(chunk)
    finally:
        response.close()

    content_type = response.headers.get("content-type", "")
    title, description = _extract_external_vacancy_text(
        b"".join(chunks),
        content_type,
        response.encoding or "",
    )
    if len(description) < 80:
        raise ValueError("could not extract enough vacancy text from URL; paste the vacancy description manually")

    return {
        "database": "",
        "id": "",
        "source": "web",
        "title": title,
        "company": "",
        "location": "",
        "url": response.url,
        "description_text": description[:12000],
        "analytics": {},
        "fetched_from_url": True,
    }


def _decode_pdf_base64(value: Any) -> bytes:
    text = _clean_text(value)
    if not text:
        return b""
    if "," in text and text.lower().startswith("data:"):
        text = text.split(",", 1)[1]
    try:
        return base64.b64decode(text, validate=True)
    except ValueError as exc:
        raise ValueError("resume PDF payload is not valid base64") from exc


def extract_resume_pdf_text(payload: dict[str, Any]) -> str:
    pdf_bytes = _decode_pdf_base64(payload.get("resume_pdf_base64"))
    if not pdf_bytes:
        return ""
    if len(pdf_bytes) > 12 * 1024 * 1024:
        raise ValueError("resume PDF is too large; use a file up to 12 MB")

    try:
        import pdfplumber
    except ImportError as exc:
        raise ValueError("PDF resume upload requires pdfplumber. Install project dependencies first.") from exc

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [(page.extract_text() or "").strip() for page in pdf.pages]
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not read resume PDF: {exc}") from exc

    text = "\n\n".join(page for page in pages if page)
    if not text:
        raise ValueError("could not extract text from resume PDF")
    return text


def build_resume_pdf_bytes(text: str, *, title: str = "Tailored Resume Draft") -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise ValueError("PDF resume export requires reportlab. Install project dependencies first.") from exc

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ResumeTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#121722"),
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "ResumeHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#d71920"),
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "ResumeBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#17202a"),
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "ResumeBullet",
        parent=body_style,
        leftIndent=10,
        firstLineIndent=-6,
    )

    story: list[Any] = [Paragraph(html.escape(title), title_style)]
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 5))
            continue
        style = body_style
        rendered = html.escape(line)
        if len(line) <= 72 and not line.endswith((".", ",", ";")) and not line.startswith("- "):
            style = heading_style
        elif line.startswith("- "):
            style = bullet_style
            rendered = "- " + html.escape(line[2:])
        story.append(Paragraph(rendered, style))

    document.build(story)
    return buffer.getvalue()


def _resume_pdf_filename(vacancy_title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", vacancy_title.lower()).strip("-")
    return f"tailored-resume-{slug or 'draft'}.pdf"


def build_resume_match(
    database_paths: Iterable[Path],
    payload: dict[str, Any],
    *,
    openai_transport: Any | None = None,
    openai_api_key: str | None = None,
) -> dict[str, Any]:
    vacancy_url = _clean_text(payload.get("vacancy_url"))
    vacancy_id = _clean_text(payload.get("vacancy_id"))
    vacancy_database = _clean_text(payload.get("vacancy_database"))
    resume_pdf_text = extract_resume_pdf_text(payload)
    resume_text = resume_pdf_text or _clean_text(payload.get("resume_text"))
    pasted_description = _clean_text(payload.get("job_description"))
    if vacancy_id:
        vacancy, database_errors = _find_resume_vacancy_by_id(database_paths, vacancy_database, vacancy_id)
        if not vacancy and vacancy_url:
            vacancy, url_database_errors = _find_resume_vacancy(database_paths, vacancy_url)
            database_errors.extend(url_database_errors)
    else:
        vacancy, database_errors = _find_resume_vacancy(database_paths, vacancy_url)
    fetched_vacancy = None
    vacancy_fetch_error = ""
    if not vacancy and vacancy_url:
        try:
            fetched_vacancy = fetch_external_vacancy(vacancy_url)
        except ValueError as exc:
            if not pasted_description:
                raise
            vacancy_fetch_error = str(exc)

    if not vacancy and not fetched_vacancy and not pasted_description:
        raise ValueError("vacancy URL was not found in local databases and could not be fetched; paste the vacancy description too")

    vacancy_source = vacancy or fetched_vacancy or {}
    vacancy_title = _clean_text(payload.get("target_title")) or vacancy_source.get("title", "")
    company = vacancy_source.get("company", "")
    vacancy_text = vacancy_source.get("description_text") or pasted_description
    analytics = vacancy_source.get("analytics", {})
    llm_match = build_llm_resume_match(
        model=_clean_text(payload.get("model")) or "gpt-5.5",
        vacancy_title=vacancy_title,
        company=company,
        vacancy_source=vacancy_source,
        vacancy_text=vacancy_text,
        analytics=analytics,
        resume_text=resume_text,
        api_key=openai_api_key,
        transport=openai_transport,
    )
    tailored_resume = llm_match["tailored_resume"]
    target_line = vacancy_title or "Target role"
    pdf_bytes = build_resume_pdf_bytes(tailored_resume, title=target_line)

    return {
        "vacancy_found": bool(vacancy),
        "vacancy_fetched": bool(fetched_vacancy),
        "vacancy_fetch_error": vacancy_fetch_error,
        "vacancy": vacancy_source or None,
        "score": llm_match["score"],
        "score_breakdown": llm_match["score_breakdown"],
        "required_keywords": [*llm_match["matched_keywords"], *llm_match["missing_keywords"]],
        "matched_keywords": llm_match["matched_keywords"],
        "missing_keywords": llm_match["missing_keywords"],
        "key_strengths": llm_match["key_strengths"],
        "critical_gaps": llm_match["critical_gaps"],
        "gap_analysis": llm_match["gap_analysis"],
        "ats_compatibility": llm_match["ats_compatibility"],
        "recommendations": llm_match["recommendations"],
        "tailored_resume": tailored_resume,
        "tailored_resume_pdf": {
            "filename": _resume_pdf_filename(target_line),
            "mime_type": "application/pdf",
            "base64": base64.b64encode(pdf_bytes).decode("ascii"),
        },
        "resume_pdf_text_extracted": bool(resume_pdf_text),
        "match_model": llm_match["model"],
        "match_confidence": llm_match["confidence"],
        "match_confidence_reason": llm_match["confidence_reason"],
        "database_errors": database_errors,
    }

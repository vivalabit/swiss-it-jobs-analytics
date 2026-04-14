from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from swiss_jobs.core.models import VacancyFull

ROLE_FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "software_engineering": (
        "software engineer",
        "software developer",
        "software architect",
        "solution architect",
        "enterprise architect",
        "softwareentwickler",
        "applikationsentwickler",
        "application engineer",
        "application developer",
        "developer",
        "entwickler",
        "backend developer",
        "backend engineer",
        "frontend developer",
        "frontend engineer",
        "full stack developer",
        "fullstack developer",
        "full stack engineer",
        "fullstack engineer",
        "web developer",
        "mobile developer",
        "ios developer",
        "android developer",
        "embedded software engineer",
        "embedded engineer",
        "research software engineer",
        "java developer",
        "python developer",
        ".net developer",
    ),
    "data_ai": (
        "data engineer",
        "data architect",
        "analytics engineer",
        "data scientist",
        "data analyst",
        "business intelligence",
        "bi developer",
        "bi analyst",
        "machine learning engineer",
        "ml engineer",
        "mlops",
        "ai engineer",
        "artificial intelligence",
        "data platform engineer",
        "dateningenieur",
        "datenwissenschaftler",
        "datenanalyst",
        "ingenieur donnees",
        "scientifique des donnees",
        "analyste de donnees",
    ),
    "devops_cloud_platform": (
        "devops engineer",
        "site reliability engineer",
        "sre",
        "platform engineer",
        "cloud engineer",
        "cloud architect",
        "infrastructure engineer",
        "system engineer",
        "system administrator",
        "systemadministrator",
        "network engineer",
        "database administrator",
        "dba",
        "linux engineer",
        "ingenieur devops",
        "administrateur systeme",
    ),
    "security": (
        "security engineer",
        "security architect",
        "cyber security",
        "cybersecurity",
        "information security",
        "soc analyst",
        "iam engineer",
        "it security",
        "ingenieur securite",
    ),
    "qa_testing": (
        "qa engineer",
        "quality engineer",
        "test engineer",
        "test automation",
        "software tester",
        "test manager",
    ),
    "support_operations": (
        "it support",
        "support engineer",
        "application support",
        "service desk",
        "helpdesk",
        "support analyst",
        "application manager",
        "workplace engineer",
        "support informatique",
    ),
    "erp_business_systems": (
        "sap consultant",
        "sap developer",
        "sap engineer",
        "sap berater",
        "sap entwickler",
        "salesforce developer",
        "salesforce consultant",
        "erp consultant",
        "erp developer",
        "dynamics 365",
    ),
    "product_project_analysis": (
        "product owner",
        "technical product manager",
        "digital product manager",
        "business analyst",
        "it business analyst",
        "technical business analyst",
        "it project manager",
        "technical project manager",
        "ict project manager",
        "scrum master",
    ),
    "ux_ui_design": (
        "ux designer",
        "ui designer",
        "product designer",
        "interaction designer",
        "ux researcher",
    ),
}

PROGRAMMING_LANGUAGE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "python": ("python",),
    "java": ("java",),
    "javascript": ("javascript",),
    "typescript": ("typescript",),
    "csharp": ("c#", "c-sharp"),
    "dotnet": (".net", "dotnet", "asp.net"),
    "php": ("php",),
    "ruby": ("ruby",),
    "go": ("golang", "go lang"),
    "rust": ("rust",),
    "scala": ("scala",),
    "kotlin": ("kotlin",),
    "swift": ("swift",),
    "r": ("r language", "rstudio", "tidyverse"),
    "sql": ("sql", "t-sql", "pl/sql"),
    "c++": ("c++",),
    "dart": ("dart",),
}

FRAMEWORK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "react": ("react",),
    "angular": ("angular",),
    "vue": ("vue", "vue.js"),
    "nodejs": ("node.js", "nodejs"),
    "nextjs": ("next.js", "nextjs"),
    "nestjs": ("nestjs", "nest.js"),
    "express": ("express.js", "express"),
    "spring": ("spring", "spring boot"),
    "django": ("django",),
    "flask": ("flask",),
    "fastapi": ("fastapi",),
    "laravel": ("laravel",),
    "symfony": ("symfony",),
    "rails": ("ruby on rails", "rails"),
    "pytorch": ("pytorch",),
    "tensorflow": ("tensorflow",),
    "scikit_learn": ("scikit-learn", "sklearn"),
    "spark": ("apache spark", "spark"),
    "airflow": ("apache airflow", "airflow"),
    "dbt": ("dbt",),
}

CLOUD_PLATFORM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "aws": ("aws", "amazon web services"),
    "azure": ("azure", "microsoft azure"),
    "gcp": ("gcp", "google cloud", "google cloud platform"),
    "openshift": ("openshift",),
    "kubernetes": ("kubernetes", "k8s"),
    "docker": ("docker", "container", "containers", "containerized"),
    "terraform": ("terraform",),
    "ansible": ("ansible",),
}

DATA_PLATFORM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "snowflake": ("snowflake",),
    "databricks": ("databricks",),
    "bigquery": ("bigquery",),
    "redshift": ("redshift",),
    "kafka": ("kafka",),
    "hadoop": ("hadoop",),
    "etl": ("etl", "elt"),
}

DATABASE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
    "mssql": ("sql server", "mssql"),
    "oracle": ("oracle",),
    "mongodb": ("mongodb", "mongo db"),
    "redis": ("redis",),
    "elasticsearch": ("elasticsearch",),
}

TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "git": (" git ", "github", "gitlab"),
    "ci_cd": ("ci/cd", "ci cd", "pipeline", "pipelines"),
    "linux": ("linux",),
    "rest_api": ("rest api", "restful api", "restful apis", "api"),
    "graphql": ("graphql",),
    "junit": ("junit",),
    "jest": ("jest",),
    "cypress": ("cypress",),
    "playwright": ("playwright",),
    "selenium": ("selenium",),
    "agile": ("agile", "scrum", "kanban"),
}

METHODOLOGY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "agile": ("agile", "scrum", "kanban"),
    "devops": ("devops",),
    "devsecops": ("devsecops",),
    "microservices": ("microservices", "microservice"),
    "clean_code": ("clean code",),
    "test_automation": ("test automation", "automated testing"),
}

SPOKEN_LANGUAGE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "english": ("english", "englisch", "anglais"),
    "german": ("german", "deutsch", "allemand"),
    "french": ("french", "francais", "franzosisch"),
    "italian": ("italian", "italienisch", "italiano"),
}

SENIORITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "intern": ("intern", "internship", "praktikum", "praktikant", "praktikantin", "stage"),
    "junior": ("junior", "entry level", "graduate", "trainee"),
    "mid": ("mid", "mid-level", "mid level", "intermediate"),
    "senior": ("senior", "sr.", "sr ", "lead", "principal", "staff"),
    "manager": ("manager", "head of", "leiter", "director"),
}

REMOTE_MODE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hybrid": ("hybrid", "home office", "mobile working", "work from home", "hybrid working"),
    "remote": ("remote", "fully remote", "telecommute"),
    "onsite": ("on-site", "onsite", "vor ort"),
}

EXPERIENCE_REQUIREMENT_PATTERN = re.compile(
    r"(?P<min>\d{1,2})\s*(?:\+|plus)?\s*(?:-|to|–|—)?\s*(?P<max>\d{1,2})?\s*"
    r"(?:years?|yrs?|jahre|ans?)"
    r"(?=[^a-z0-9]{0,20}(?:of\s+)?(?:professional|relevant|practical|hands[- ]on)?"
    r"[^a-z0-9]{0,20}(?:experience|erfahrung|expérience))",
    re.IGNORECASE,
)


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_text(parts: Sequence[str]) -> str:
    text = " ".join(part for part in parts if part)
    return f" {_normalize_spaces(text).lower()} "


def _contains_alias(text: str, alias: str) -> bool:
    normalized_alias = alias.lower().strip()
    if not normalized_alias:
        return False
    pattern = re.compile(
        rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))


def _collect_matches(text: str, catalog: Mapping[str, Sequence[str]]) -> list[str]:
    matches: list[str] = []
    for key, aliases in catalog.items():
        if any(_contains_alias(text, alias) for alias in aliases):
            matches.append(key)
    return matches


def _coerce_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        clean = _normalize_spaces(value)
        return [clean] if clean else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result: list[str] = []
        for item in value:
            result.extend(_coerce_strings(item))
        return result
    return []


def _extract_occupational_categories(schema: Mapping[str, Any]) -> list[str]:
    return _coerce_strings(schema.get("occupationalCategory"))


def _extract_employment_types(vacancy: VacancyFull, schema: Mapping[str, Any]) -> list[str]:
    employment_types = _coerce_strings(schema.get("employmentType"))
    if employment_types:
        return employment_types
    for key in ("employmentType", "employment_type", "jobType", "employmentTypeText"):
        employment_types.extend(_coerce_strings(vacancy.raw.get(key)))
    return _dedupe_strings(employment_types)


def _extract_workload(vacancy: VacancyFull) -> dict[str, int] | None:
    raw_grades = vacancy.raw.get("employmentGrades")
    values: list[int] = []
    if isinstance(raw_grades, Sequence) and not isinstance(raw_grades, (str, bytes, bytearray)):
        values.extend(int(item) for item in raw_grades if isinstance(item, int))
    if values:
        return {
            "min": min(values),
            "max": max(values),
        }

    for key in ("employmentGrade", "workload"):
        parsed = _parse_percentages_from_text(str(vacancy.raw.get(key) or ""))
        if parsed:
            return parsed
    return None


def _extract_workload_text(vacancy: VacancyFull) -> str | None:
    raw_grades = vacancy.raw.get("employmentGrades")
    if isinstance(raw_grades, Sequence) and not isinstance(raw_grades, (str, bytes, bytearray)):
        values = [int(item) for item in raw_grades if isinstance(item, int)]
        if values:
            low = min(values)
            high = max(values)
            if low == high:
                return f"{low}%"
            return f"{low}% - {high}%"

    for key in ("employmentGrade", "workload"):
        value = str(vacancy.raw.get(key) or "").strip()
        if value:
            return value
    return None


def _parse_percentages_from_text(value: str) -> dict[str, int] | None:
    matches = [int(item) for item in re.findall(r"(\d{1,3})\s*%", value)]
    if not matches:
        return None
    return {
        "min": min(matches),
        "max": max(matches),
    }


def _extract_address(vacancy: VacancyFull, schema: Mapping[str, Any]) -> dict[str, str] | None:
    job_location = schema.get("jobLocation")
    if isinstance(job_location, list):
        job_location = job_location[0] if job_location else None
    if isinstance(job_location, Mapping):
        address = job_location.get("address")
        if isinstance(address, Mapping):
            payload = {
                "street_address": str(address.get("streetAddress") or "").strip(),
                "locality": str(address.get("addressLocality") or "").strip(),
                "postal_code": str(address.get("postalCode") or "").strip(),
                "region": str(address.get("addressRegion") or "").strip(),
                "country": str(address.get("addressCountry") or "").strip(),
            }
            pruned = _prune(payload)
            if pruned:
                return pruned

    fallback = {
        "locality": vacancy.place,
    }
    raw_location_slug = str(vacancy.raw.get("jobLocationSlug") or "").strip()
    if raw_location_slug:
        fallback["job_location_slug"] = raw_location_slug
    return _prune(fallback)


def _extract_salary(vacancy: VacancyFull, schema: Mapping[str, Any]) -> dict[str, Any] | None:
    base_salary = schema.get("baseSalary")
    if isinstance(base_salary, Mapping):
        payload: dict[str, Any] = {
            "currency": str(base_salary.get("currency") or "").strip(),
        }
        value = base_salary.get("value")
        if isinstance(value, Mapping):
            if value.get("minValue") is not None:
                payload["min"] = value.get("minValue")
            if value.get("maxValue") is not None:
                payload["max"] = value.get("maxValue")
            if value.get("value") is not None:
                payload["value"] = value.get("value")
            if value.get("unitText") is not None:
                payload["unit"] = str(value.get("unitText") or "").strip()
        elif value is not None:
            payload["value"] = value

        pruned = _prune(payload)
        if pruned:
            return pruned

    raw_salary = vacancy.raw.get("salary")
    if isinstance(raw_salary, Mapping):
        salary_range = raw_salary.get("range")
        payload = {
            "currency": str(raw_salary.get("currency") or "").strip(),
            "unit": str(raw_salary.get("unit") or "").strip(),
        }
        if isinstance(salary_range, Mapping):
            if salary_range.get("minValue") is not None:
                payload["min"] = salary_range.get("minValue")
            if salary_range.get("maxValue") is not None:
                payload["max"] = salary_range.get("maxValue")
        pruned = _prune(payload)
        if pruned:
            return pruned

    for key in ("salaryText", "salary_text", "salaryFormatted", "salary"):
        value = vacancy.raw.get(key)
        if isinstance(value, str) and value.strip():
            return {"text": value.strip()}
    return None


def _extract_company(vacancy: VacancyFull, schema: Mapping[str, Any]) -> dict[str, str] | None:
    organization = schema.get("hiringOrganization")
    if isinstance(organization, Mapping):
        payload = {
            "name": str(organization.get("name") or "").strip(),
            "website": str(organization.get("sameAs") or "").strip(),
            "logo": str(organization.get("logo") or "").strip(),
        }
        pruned = _prune(payload)
        if pruned:
            return pruned

    raw_company = vacancy.raw.get("company")
    if isinstance(raw_company, Mapping):
        payload = {
            "name": str(raw_company.get("name") or vacancy.company).strip(),
            "website": str(raw_company.get("sameAs") or raw_company.get("website") or "").strip(),
            "logo": str(
                raw_company.get("logo")
                or (raw_company.get("logoImage") or {}).get("src")
                or vacancy.raw.get("logo")
                or ""
            ).strip(),
        }
        pruned = _prune(payload)
        if pruned:
            return pruned

    return _prune({"name": vacancy.company})


def _extract_listing_tags(vacancy: VacancyFull) -> list[str]:
    tags: list[str] = []
    for key in ("listingTags", "tags"):
        raw_tags = vacancy.raw.get(key)
        if not isinstance(raw_tags, Sequence) or isinstance(raw_tags, (str, bytes, bytearray)):
            continue
        for item in raw_tags:
            if isinstance(item, Mapping):
                tag_name = str(item.get("name") or item.get("label") or "").strip()
            else:
                tag_name = str(item).strip()
            if tag_name:
                tags.append(tag_name)
    return _dedupe_strings(tags)


def _extract_remote_mode(text: str, schema: Mapping[str, Any]) -> str | None:
    job_location_type = str(schema.get("jobLocationType") or "").strip().lower()
    if "telecommute" in job_location_type or "remote" in job_location_type:
        return "remote"

    for mode in ("hybrid", "remote", "onsite"):
        if any(_contains_alias(text, alias) for alias in REMOTE_MODE_KEYWORDS[mode]):
            return mode
    return None


def _extract_raw_language_skills(vacancy: VacancyFull) -> list[str]:
    raw_value = vacancy.raw.get("languageSkills")
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
        return []

    collected: list[str] = []
    for item in raw_value:
        if isinstance(item, str):
            collected.append(item)
            continue
        if isinstance(item, Mapping):
            for key in ("name", "language", "title", "label"):
                label = str(item.get(key) or "").strip()
                if label:
                    collected.append(label)
                    break
    normalized = _normalize_text(collected)
    return _collect_matches(normalized, SPOKEN_LANGUAGE_KEYWORDS)


def _extract_experience_years(text: str) -> dict[str, int] | None:
    matches: list[tuple[int, int | None]] = []
    for match in EXPERIENCE_REQUIREMENT_PATTERN.finditer(text):
        minimum = int(match.group("min"))
        maximum = match.group("max")
        matches.append((minimum, int(maximum) if maximum else None))

    if not matches:
        return None

    minimum, maximum = max(matches, key=lambda item: item[0])
    payload: dict[str, int] = {"min": minimum}
    if maximum is not None:
        payload["max"] = maximum
    return payload


def _infer_seniority_labels(
    explicit_labels: Sequence[str],
    experience_years: Mapping[str, int] | None,
) -> list[str]:
    labels = list(explicit_labels)
    if any(label in {"intern", "junior", "senior", "manager"} for label in labels):
        return _dedupe_strings(labels)
    if not experience_years:
        return _dedupe_strings(labels)

    minimum_years = int(experience_years.get("min") or 0)
    inferred: str | None = None
    if minimum_years >= 5:
        inferred = "senior"
    elif minimum_years >= 3:
        inferred = "mid"
    elif minimum_years >= 1:
        inferred = "junior"

    if inferred and inferred not in labels:
        labels.append(inferred)
    return _dedupe_strings(labels)


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        clean = _normalize_spaces(str(item))
        lowered = clean.casefold()
        if not clean or lowered in seen:
            continue
        seen.add(lowered)
        result.append(clean)
    return result


def _prune(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            cleaned = _prune(item)
            if cleaned in (None, "", [], {}):
                continue
            result[key] = cleaned
        return result
    if isinstance(value, list):
        result = [_prune(item) for item in value]
        return [item for item in result if item not in (None, "", [], {})]
    return value


def build_job_analytics(vacancy: VacancyFull) -> dict[str, Any]:
    schema = vacancy.job_posting_schema or {}
    occupational_categories = _extract_occupational_categories(schema)
    listing_tags = _extract_listing_tags(vacancy)
    employment_types = _extract_employment_types(vacancy, schema)
    text = _normalize_text(
        [
            vacancy.title,
            vacancy.place,
            vacancy.description_text,
            vacancy.description_html,
            " ".join(occupational_categories),
            " ".join(listing_tags),
            " ".join(employment_types),
            str(schema.get("industry") or ""),
        ]
    )
    title_text = _normalize_text([vacancy.title, " ".join(occupational_categories)])

    role_family_matches = _collect_matches(title_text, ROLE_FAMILY_KEYWORDS)
    if not role_family_matches:
        role_family_matches = _collect_matches(text, ROLE_FAMILY_KEYWORDS)

    spoken_languages = _collect_matches(text, SPOKEN_LANGUAGE_KEYWORDS)
    for language in _extract_raw_language_skills(vacancy):
        if language not in spoken_languages:
            spoken_languages.append(language)

    experience_years = _extract_experience_years(text)
    seniority_labels = _infer_seniority_labels(
        _collect_matches(text, SENIORITY_KEYWORDS),
        experience_years,
    )

    analytics = {
        "normalized_title": _normalize_spaces(vacancy.title),
        "role_family_primary": role_family_matches[0] if role_family_matches else None,
        "role_family_matches": role_family_matches,
        "seniority_labels": seniority_labels,
        "experience_years": experience_years,
        "programming_languages": _collect_matches(text, PROGRAMMING_LANGUAGE_KEYWORDS),
        "frameworks_libraries": _collect_matches(text, FRAMEWORK_KEYWORDS),
        "cloud_platforms": _collect_matches(text, CLOUD_PLATFORM_KEYWORDS),
        "data_platforms": _collect_matches(text, DATA_PLATFORM_KEYWORDS),
        "databases": _collect_matches(text, DATABASE_KEYWORDS),
        "tools_platforms": _collect_matches(text, TOOL_KEYWORDS),
        "methodologies": _collect_matches(text, METHODOLOGY_KEYWORDS),
        "spoken_languages": spoken_languages,
        "employment_types": employment_types,
        "occupational_categories": occupational_categories,
        "industry": str(schema.get("industry") or "").strip() or None,
        "remote_mode": _extract_remote_mode(text, schema),
        "workload_percent": _extract_workload(vacancy),
        "workload_text": _extract_workload_text(vacancy),
        "salary": _extract_salary(vacancy, schema),
        "company": _extract_company(vacancy, schema),
        "job_location": _extract_address(vacancy, schema),
        "listing_tags": listing_tags,
    }
    return _prune(analytics)

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Literal

SkillCategory = Literal[
    "language",
    "framework",
    "cloud",
    "database",
    "methodology",
    "tool",
    "domain",
]

SKILL_CATEGORIES: tuple[SkillCategory, ...] = (
    "language",
    "framework",
    "cloud",
    "database",
    "methodology",
    "tool",
    "domain",
)


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    key: str
    category: SkillCategory
    aliases: tuple[str, ...]
    legacy_field: str | None = None
    negative_contexts: tuple[str, ...] = ()


SKILL_TAXONOMY: tuple[SkillDefinition, ...] = (
    SkillDefinition("c", "language", ("ansi c", "embedded c", "c/c++", "c/c++20", "c / c++"), "programming_languages"),
    SkillDefinition("python", "language", ("python",), "programming_languages"),
    SkillDefinition(
        "java",
        "language",
        ("java",),
        "programming_languages",
        negative_contexts=(r"\bjava\s+(?:island|coffee|beans?)\b", r"\bisland\s+of\s+java\b"),
    ),
    SkillDefinition("javascript", "language", ("javascript", "js"), "programming_languages"),
    SkillDefinition("typescript", "language", ("typescript",), "programming_languages"),
    SkillDefinition("csharp", "language", ("c#", "c-sharp"), "programming_languages"),
    SkillDefinition("dotnet", "language", (".net", ".net core", "dotnet", "asp.net"), "programming_languages"),
    SkillDefinition("php", "language", ("php",), "programming_languages"),
    SkillDefinition("ruby", "language", ("ruby",), "programming_languages"),
    SkillDefinition("go", "language", ("golang", "go lang"), "programming_languages"),
    SkillDefinition("rust", "language", ("rust",), "programming_languages"),
    SkillDefinition("scala", "language", ("scala",), "programming_languages"),
    SkillDefinition("kotlin", "language", ("kotlin",), "programming_languages"),
    SkillDefinition(
        "swift",
        "language",
        ("swift",),
        "programming_languages",
        negative_contexts=(r"\bswift\s+(?:response|action|delivery|decision)\b",),
    ),
    SkillDefinition("r", "language", ("r language", "rstudio", "tidyverse"), "programming_languages"),
    SkillDefinition("sql", "language", ("sql", "t-sql", "pl/sql"), "programming_languages"),
    SkillDefinition("c++", "language", ("c++",), "programming_languages"),
    SkillDefinition("dart", "language", ("dart",), "programming_languages"),
    SkillDefinition("react", "framework", ("react",), "frameworks_libraries"),
    SkillDefinition("angular", "framework", ("angular",), "frameworks_libraries"),
    SkillDefinition("vue", "framework", ("vue", "vue.js"), "frameworks_libraries"),
    SkillDefinition("nodejs", "framework", ("node.js", "nodejs"), "frameworks_libraries"),
    SkillDefinition("nextjs", "framework", ("next.js", "nextjs"), "frameworks_libraries"),
    SkillDefinition("nestjs", "framework", ("nestjs", "nest.js"), "frameworks_libraries"),
    SkillDefinition("express", "framework", ("express.js", "express"), "frameworks_libraries"),
    SkillDefinition("spring", "framework", ("spring", "spring boot"), "frameworks_libraries"),
    SkillDefinition("django", "framework", ("django",), "frameworks_libraries"),
    SkillDefinition("flask", "framework", ("flask",), "frameworks_libraries"),
    SkillDefinition("fastapi", "framework", ("fastapi",), "frameworks_libraries"),
    SkillDefinition("laravel", "framework", ("laravel",), "frameworks_libraries"),
    SkillDefinition("symfony", "framework", ("symfony",), "frameworks_libraries"),
    SkillDefinition("rails", "framework", ("ruby on rails", "rails"), "frameworks_libraries"),
    SkillDefinition("pytorch", "framework", ("pytorch",), "frameworks_libraries"),
    SkillDefinition("tensorflow", "framework", ("tensorflow",), "frameworks_libraries"),
    SkillDefinition("scikit_learn", "framework", ("scikit-learn", "sklearn"), "frameworks_libraries"),
    SkillDefinition("spark", "framework", ("apache spark", "spark"), "frameworks_libraries"),
    SkillDefinition("airflow", "framework", ("apache airflow", "airflow"), "frameworks_libraries"),
    SkillDefinition("dbt", "framework", ("dbt",), "frameworks_libraries"),
    SkillDefinition("numpy", "framework", ("numpy",), "frameworks_libraries"),
    SkillDefinition("pandas", "framework", ("pandas",), "frameworks_libraries"),
    SkillDefinition("or_tools", "framework", ("or-tools", "or tools", "google or-tools", "google or tools"), "frameworks_libraries"),
    SkillDefinition("cp_sat", "framework", ("cp-sat", "cp sat", "cpsat"), "frameworks_libraries"),
    SkillDefinition("boost", "framework", ("boost", "boost c++"), "frameworks_libraries"),
    SkillDefinition("aws", "cloud", ("aws", "amazon web services"), "cloud_platforms"),
    SkillDefinition(
        "azure",
        "cloud",
        (
            "microsoft azure",
            "azure cloud",
            "azure services",
            "azure infrastructure",
            "azure kubernetes service",
            "azure functions",
        ),
        "cloud_platforms",
    ),
    SkillDefinition("gcp", "cloud", ("gcp", "google cloud", "google cloud platform"), "cloud_platforms"),
    SkillDefinition("postgresql", "database", ("postgresql", "postgres"), "databases"),
    SkillDefinition("mysql", "database", ("mysql",), "databases"),
    SkillDefinition("mssql", "database", ("sql server", "mssql"), "databases"),
    SkillDefinition("oracle", "database", ("oracle",), "databases"),
    SkillDefinition("mongodb", "database", ("mongodb", "mongo db"), "databases"),
    SkillDefinition("redis", "database", ("redis",), "databases"),
    SkillDefinition("elasticsearch", "database", ("elasticsearch",), "databases"),
    SkillDefinition("snowflake", "database", ("snowflake",), "data_platforms"),
    SkillDefinition("bigquery", "database", ("bigquery",), "data_platforms"),
    SkillDefinition("redshift", "database", ("redshift",), "data_platforms"),
    SkillDefinition("terraform", "tool", ("terraform",), "cloud_platforms"),
    SkillDefinition("ansible", "tool", ("ansible",), "cloud_platforms"),
    SkillDefinition("databricks", "tool", ("databricks",), "data_platforms"),
    SkillDefinition("kafka", "tool", ("kafka",), "data_platforms"),
    SkillDefinition("hadoop", "tool", ("hadoop",), "data_platforms"),
    SkillDefinition("etl", "domain", ("etl", "elt"), "data_platforms"),
    SkillDefinition("openshift", "tool", ("openshift",), "platforms"),
    SkillDefinition("kubernetes", "tool", ("kubernetes", "k8s"), "platforms"),
    SkillDefinition("docker", "tool", ("docker", "dockerfile", "docker compose", "docker-compose"), "platforms"),
    SkillDefinition("plc", "domain", ("plc", "programmable logic controller"), "platforms"),
    SkillDefinition("vmware_esxi", "tool", ("vmware esxi", "esxi"), "platforms"),
    SkillDefinition("git", "tool", ("git", "github", "gitlab"), "tools"),
    SkillDefinition("azure_devops", "tool", ("azure devops",), "tools"),
    SkillDefinition("visual_studio", "tool", ("visual studio",), "tools"),
    SkillDefinition("camunda", "tool", ("camunda",), "tools"),
    SkillDefinition("flowable", "tool", ("flowable",), "tools"),
    SkillDefinition("powershell", "tool", ("powershell", "power shell"), "tools"),
    SkillDefinition("batch", "tool", ("batch scripting", "batch script", "batch files", ".bat"), "tools"),
    SkillDefinition("linux", "tool", ("linux",), "tools"),
    SkillDefinition("junit", "tool", ("junit",), "tools"),
    SkillDefinition("jest", "tool", ("jest",), "tools"),
    SkillDefinition("cypress", "tool", ("cypress",), "tools"),
    SkillDefinition("playwright", "tool", ("playwright",), "tools"),
    SkillDefinition("selenium", "tool", ("selenium",), "tools"),
    SkillDefinition("excel", "tool", ("excel", "microsoft excel"), "tools"),
    SkillDefinition("power_bi", "tool", ("power bi", "powerbi"), "tools"),
    SkillDefinition("tableau", "tool", ("tableau",), "tools"),
    SkillDefinition(
        "rest",
        "tool",
        ("rest api", "restful api", "restful apis", "rest"),
        "protocols_standards",
        negative_contexts=(r"\brest\s+of\b", r"\btake\s+(?:a\s+)?rest\b", r"\brest\s+assured\b"),
    ),
    SkillDefinition("graphql", "tool", ("graphql",), "protocols_standards"),
    SkillDefinition("opc_ua", "domain", ("opc-ua", "opc ua"), "protocols_standards"),
    SkillDefinition("tcp_ip", "domain", ("tcp/ip", "tcp ip"), "protocols_standards"),
    SkillDefinition("beckhoff", "domain", ("beckhoff",), "vendors"),
    SkillDefinition("siemens", "domain", ("siemens",), "vendors"),
    SkillDefinition("vmware", "tool", ("vmware",), "vendors"),
    SkillDefinition("agile", "methodology", ("agile", "scrum", "kanban"), "methodologies"),
    SkillDefinition("ci_cd", "methodology", ("ci/cd", "ci cd", "continuous integration", "continuous delivery"), "methodologies"),
    SkillDefinition("devops", "methodology", ("devops",), "methodologies"),
    SkillDefinition("devsecops", "methodology", ("devsecops",), "methodologies"),
    SkillDefinition("microservices", "methodology", ("microservices", "microservice"), "methodologies"),
    SkillDefinition("clean_code", "methodology", ("clean code",), "methodologies"),
    SkillDefinition("test_automation", "methodology", ("test automation", "automated testing"), "methodologies"),
    SkillDefinition("business_intelligence", "domain", ("business intelligence", "bi reporting", "bi analytics"), None),
    SkillDefinition("machine_learning", "domain", ("machine learning", "mlops"), None),
    SkillDefinition("cyber_security", "domain", ("cyber security", "cybersecurity", "information security"), None),
    SkillDefinition("erp", "domain", ("erp", "sap"), None),
)

SKILL_BY_KEY: dict[str, SkillDefinition] = {definition.key: definition for definition in SKILL_TAXONOMY}
SKILL_CATEGORY_BY_KEY: dict[str, SkillCategory] = {
    definition.key: definition.category for definition in SKILL_TAXONOMY
}
_ALIAS_TO_KEY: dict[str, str]


def build_skill_alias_catalog(
    *,
    category: SkillCategory | None = None,
    legacy_field: str | None = None,
) -> dict[str, tuple[str, ...]]:
    return {
        definition.key: definition.aliases
        for definition in _iter_definitions(category=category, legacy_field=legacy_field)
    }


def collect_skill_matches(
    text: str,
    *,
    category: SkillCategory | None = None,
    legacy_field: str | None = None,
) -> list[str]:
    normalized_text = normalize_text_for_matching([text])
    matches: list[str] = []
    for definition in _iter_definitions(category=category, legacy_field=legacy_field):
        if _definition_matches(normalized_text, definition):
            matches.append(definition.key)
    return matches


def canonicalize_skill(value: Any, *, allow_unknown: bool = False) -> str | None:
    if value is None:
        return None

    text = " ".join(str(value).strip().split())
    if not text:
        return None

    normalized = _normalize_lookup_text(text)
    canonical = _ALIAS_TO_KEY.get(normalized)
    if canonical is not None:
        return canonical
    return text.casefold() if allow_unknown else None


def categorize_skills(values: Iterable[Any]) -> dict[SkillCategory, list[str]]:
    categorized: dict[SkillCategory, list[str]] = {category: [] for category in SKILL_CATEGORIES}
    seen: set[tuple[SkillCategory, str]] = set()
    for value in values:
        canonical = canonicalize_skill(value)
        if canonical is None:
            continue
        category = SKILL_CATEGORY_BY_KEY[canonical]
        marker = (category, canonical)
        if marker in seen:
            continue
        seen.add(marker)
        categorized[category].append(canonical)
    return categorized


def build_skill_taxonomy_records(values: Iterable[Any]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for category, skills in categorize_skills(values).items():
        for skill in skills:
            records.append({"category": category, "skill": skill})
    return records


def category_for_skill(value: Any) -> SkillCategory | None:
    canonical = canonicalize_skill(value)
    if canonical is None:
        return None
    return SKILL_CATEGORY_BY_KEY[canonical]


def normalize_text_for_matching(parts: Iterable[str]) -> str:
    text = " ".join(part for part in parts if part)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u2010-\u2015/_?:]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return f" {text} " if text else " "


def _iter_definitions(
    *,
    category: SkillCategory | None,
    legacy_field: str | None,
) -> Iterable[SkillDefinition]:
    for definition in SKILL_TAXONOMY:
        if category is not None and definition.category != category:
            continue
        if legacy_field is not None and definition.legacy_field != legacy_field:
            continue
        yield definition


def _definition_matches(text: str, definition: SkillDefinition) -> bool:
    for alias in definition.aliases:
        normalized_alias = _normalize_alias_for_matching(alias)
        if not normalized_alias:
            continue
        pattern = re.compile(
            rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            if not _is_negative_context(text, match, definition.negative_contexts):
                return True
    return False


def _is_negative_context(
    text: str,
    match: re.Match[str],
    negative_contexts: tuple[str, ...],
) -> bool:
    if not negative_contexts:
        return False
    start = max(0, match.start() - 80)
    end = min(len(text), match.end() + 80)
    context = text[start:end]
    return any(re.search(pattern, context, flags=re.IGNORECASE) for pattern in negative_contexts)


def _normalize_alias_for_matching(value: str) -> str:
    return normalize_text_for_matching([value]).strip()


def _normalize_lookup_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"[\u2010-\u2015/_?:]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text


_ALIAS_TO_KEY = {}
for _definition in SKILL_TAXONOMY:
    _ALIAS_TO_KEY[_normalize_lookup_text(_definition.key)] = _definition.key
    for _alias in _definition.aliases:
        _ALIAS_TO_KEY[_normalize_lookup_text(_alias)] = _definition.key

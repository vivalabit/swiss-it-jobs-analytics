from __future__ import annotations

CANONICAL_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "vacancy_id": ("vacancy_id", "id", "job_id", "vacancyid"),
    "company": ("company", "company_name", "employer", "hiring_organization"),
    "role_category": (
        "role_category",
        "role_family_primary",
        "role_family",
        "role",
        "category",
    ),
    "city": ("city", "place", "location_city", "locality"),
    "canton": ("canton", "state", "region", "location_canton"),
    "seniority": ("seniority", "seniority_level", "experience_level"),
    "work_mode": ("work_mode", "remote_mode", "remote_policy"),
    "skills": (
        "skills",
        "skill_tags",
        "detected_skills",
        "keywords_matched",
        "tech_skills",
    ),
    "programming_languages": (
        "programming_languages",
        "programming_language",
        "languages",
        "language_skills",
    ),
    "frameworks_libraries": (
        "frameworks_libraries",
        "frameworks",
        "framework_libraries",
        "libraries",
        "framework_library",
    ),
    "salary_min": ("salary_min", "salary_from", "annual_salary_from", "min_salary"),
    "salary_max": ("salary_max", "salary_to", "annual_salary_to", "max_salary"),
    "salary_currency": ("salary_currency", "currency"),
    "salary_unit": ("salary_unit", "salary_period", "salary_frequency", "unit"),
    "salary_text": ("salary_text", "salary", "salary_display"),
}

REQUIRED_COLUMNS: tuple[str, ...] = (
    "company",
    "role_category",
    "city",
    "canton",
    "seniority",
    "work_mode",
    "skills",
)

DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "company",
    "role_category",
    "city",
    "canton",
    "seniority",
    "work_mode",
)

MISSING_TEXT_VALUES: frozenset[str] = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "none",
        "null",
        "nan",
        "unknown",
        "not specified",
        "not_specified",
    }
)

UNKNOWN_LABEL = "Unknown"
STAFFING_AGENCY_COMPANY_NAMES: frozenset[str] = frozenset(
    {
        "Adecco",
        "albedis",
        "Art of Work Personalberatung AG",
        "bruederlinpartner GmbH",
        "Careerplus AG",
        "Consult & Pepper AG",
        "Experis",
        "Experis AG",
        "Freestar-Informatik AG",
        "Hays",
        "Impact Recruitment GmbH",
        "ITech Consult AG",
        "ictjobs (Stellenmarkt)",
        "IQ Plus AG",
        "Job Impuls AG",
        "Manpower",
        "Michael Page",
        "mühlemann IT-personal",
        "myitjob GmbH",
        "myScience",
        "Nemensis AG",
        "Nexus Personal- & Unternehmensberatung AG",
        "ONE Agency GmbH",
        "Page Personnel",
        "persona service GmbH",
        "Prime21",
        "Prime21 AG",
        "Progress Personal AG",
        "Randstad",
        "Randstad (Schweiz) AG",
        "Rocken®",
        "Rockstar Recruiting AG",
        "Summit Recruitment AG",
        "Universal-Job AG",
        "Work Selection",
        "yellowshark",
    }
)
DEFAULT_TOP_SKILLS = 20
DEFAULT_TOP_SKILL_PAIRS = 50
OPTIONAL_LIST_COLUMNS: tuple[str, ...] = (
    "programming_languages",
    "frameworks_libraries",
)

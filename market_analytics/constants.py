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
DEFAULT_TOP_SKILLS = 20
DEFAULT_TOP_SKILL_PAIRS = 50

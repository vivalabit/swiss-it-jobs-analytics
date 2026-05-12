from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import VacancyFull


@dataclass(frozen=True, slots=True)
class SalaryInfo:
    minimum: int | None = None
    maximum: int | None = None
    currency: str | None = None
    unit: str | None = None
    text: str | None = None

    @property
    def display_text(self) -> str | None:
        if self.text:
            return self.text

        currency_prefix = f"{self.currency} " if self.currency else ""
        unit_suffix = f" / {self.unit.lower()}" if self.unit else ""
        if self.minimum is not None and self.maximum is not None:
            if self.minimum == self.maximum:
                return f"{currency_prefix}{self.minimum}{unit_suffix}".strip()
            return f"{currency_prefix}{self.minimum}-{self.maximum}{unit_suffix}".strip()
        if self.minimum is not None:
            return f"{currency_prefix}{self.minimum}{unit_suffix}".strip()
        if self.maximum is not None:
            return f"{currency_prefix}{self.maximum}{unit_suffix}".strip()
        return None


def extract_salary_info(vacancy: VacancyFull) -> SalaryInfo:
    raw = vacancy.raw or {}
    raw_salary = raw.get("salary")
    if isinstance(raw_salary, Mapping):
        minimum, maximum = _extract_salary_range(raw_salary.get("range"))
        return SalaryInfo(
            minimum=minimum,
            maximum=maximum,
            currency=_clean_text(raw_salary.get("currency")),
            unit=_clean_text(raw_salary.get("unit")),
            text=_extract_salary_text(raw),
        )

    schema = vacancy.job_posting_schema or {}
    base_salary = schema.get("baseSalary")
    if isinstance(base_salary, Mapping):
        value = base_salary.get("value")
        minimum = None
        maximum = None
        unit = None
        if isinstance(value, Mapping):
            minimum = _coerce_optional_int(value.get("minValue"))
            maximum = _coerce_optional_int(value.get("maxValue"))
            single_value = _coerce_optional_int(value.get("value"))
            if single_value is not None:
                minimum = minimum if minimum is not None else single_value
                maximum = maximum if maximum is not None else single_value
            unit = _clean_text(value.get("unitText"))
        else:
            single_value = _coerce_optional_int(value)
            if single_value is not None:
                minimum = single_value
                maximum = single_value
        return SalaryInfo(
            minimum=minimum,
            maximum=maximum,
            currency=_clean_text(base_salary.get("currency")),
            unit=unit,
            text=_extract_salary_text(raw),
        )

    return SalaryInfo(text=_extract_salary_text(raw))


def parse_salary_range_text(value: str) -> SalaryInfo | None:
    compact = " ".join(value.split())
    number_pattern = r"(?:\d{1,3}(?:[\s'’.,]\d{3})+|\d+)"
    match = re.search(
        r"(?P<currency>CHF|EUR|USD|GBP)\s*"
        rf"(?P<minimum>{number_pattern})\s*(?:-|–|—|to|bis)\s*"
        rf"(?P<maximum>{number_pattern})"
        r"(?:\s*(?:/|per|pro)\s*(?P<unit>an|year|jahr|mois|month|monat|heure|hour|stunde))?",
        compact,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    minimum = _parse_salary_number(match.group("minimum"))
    maximum = _parse_salary_number(match.group("maximum"))
    if minimum is None or maximum is None:
        return None

    unit = _normalize_salary_unit(str(match.group("unit") or "").strip().lower())
    if unit is None and max(minimum, maximum) >= 1000:
        unit = "YEAR"

    return SalaryInfo(
        minimum=minimum,
        maximum=maximum,
        currency=str(match.group("currency") or "").upper(),
        unit=unit,
    )


def _extract_salary_range(value: Any) -> tuple[int | None, int | None]:
    if not isinstance(value, Mapping):
        return (None, None)
    return (_coerce_optional_int(value.get("minValue")), _coerce_optional_int(value.get("maxValue")))


def _extract_salary_text(raw: Mapping[str, Any]) -> str | None:
    for key in ("salaryText", "salary_text", "salaryFormatted", "salary"):
        value = raw.get(key)
        if isinstance(value, str):
            clean = value.strip()
            if clean:
                return clean
    return None


def _coerce_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return _parse_salary_number(value)
    return None


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    return clean or None


def _parse_salary_number(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return None
    return int(digits)


def _normalize_salary_unit(value: str) -> str | None:
    mapping = {
        "an": "YEAR",
        "year": "YEAR",
        "jahr": "YEAR",
        "mois": "MONTH",
        "month": "MONTH",
        "monat": "MONTH",
        "heure": "HOUR",
        "hour": "HOUR",
        "stunde": "HOUR",
    }
    return mapping.get(value) if value else None

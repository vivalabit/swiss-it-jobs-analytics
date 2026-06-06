from __future__ import annotations

import re
import unicodedata

IGNORED_LOCATION_TOKENS = {
    "ag",
    "ai",
    "ar",
    "be",
    "bl",
    "bs",
    "ch",
    "che",
    "fr",
    "ge",
    "gl",
    "gr",
    "ju",
    "lu",
    "ne",
    "nw",
    "ow",
    "sg",
    "sh",
    "so",
    "sz",
    "tg",
    "ti",
    "ur",
    "vd",
    "vs",
    "zg",
    "zh",
    "aargau",
    "appenzell ausserrhoden",
    "appenzell innerrhoden",
    "fribourg",
    "freiburg",
    "glarus",
    "graubunden",
    "grisons",
    "jura",
    "neuenburg",
    "nidwalden",
    "obwalden",
    "ch",
    "schweiz",
    "schwyz",
    "suisse",
    "svizzera",
    "switzerland",
    "thurgau",
    "ticino",
    "uri",
    "valais",
    "vaud",
    "wallis",
}

GENERIC_LOCATION_WORDS = {
    "area",
    "canton",
    "canton de",
    "greater",
    "kanton",
    "metropolitan",
    "region",
}

LOCATION_DISPLAY_ALIASES: dict[str, str] = {
    "basle": "Basel",
    "basel": "Basel",
    "bern": "Bern",
    "berne": "Bern",
    "geneva": "Genève",
    "geneve": "Genève",
    "genf": "Genève",
    "genève": "Genève",
    "lucerne": "Luzern",
    "luzern": "Luzern",
    "neuchatel": "Neuchâtel",
    "neuchâtel": "Neuchâtel",
    "zurich": "Zürich",
    "zuerich": "Zürich",
    "zürich": "Zürich",
}

LOCATION_SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "Basel": ("basel", "basle"),
    "Bern": ("bern", "berne"),
    "Genève": ("geneva", "geneve", "genève", "genf"),
    "Luzern": ("lucerne", "luzern"),
    "Neuchâtel": ("neuchatel", "neuchâtel"),
    "Zürich": ("zurich", "zuerich", "zürich"),
}


def normalize_location_display(value: object) -> str:
    text = _clean_location_text(value)
    if not text:
        return ""

    parts = _split_location_parts(text)
    normalized_parts: list[str] = []
    seen: set[str] = set()
    for part in parts:
        canonical = _canonical_location_part(part)
        if not canonical:
            continue
        key = _normalize_key(canonical)
        if key in seen:
            continue
        seen.add(key)
        normalized_parts.append(canonical)

    return " / ".join(normalized_parts)


def location_search_terms(value: object) -> list[str]:
    canonical = normalize_location_display(value)
    terms: list[str] = []
    terms.extend(_split_location_parts(_clean_location_text(value)))
    if canonical:
        terms.extend(canonical.split(" / "))

    for display, aliases in LOCATION_SEARCH_ALIASES.items():
        if canonical == display or _normalize_key(value) in {_normalize_key(alias) for alias in aliases}:
            terms.append(display)
            terms.extend(aliases)

    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean = _clean_location_text(term)
        if not clean:
            continue
        variants = {clean, _strip_accents(clean)}
        for variant in variants:
            key = variant.lower()
            if key and key not in seen:
                seen.add(key)
                result.append(key)
    return result


def _clean_location_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;/|")


def _split_location_parts(value: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", " ", value)
    raw_parts = re.split(r"\s*(?:,|;|\||/|\n|•|\+|\band\b|\bund\b)\s*", text, flags=re.IGNORECASE)
    return [_clean_location_text(part) for part in raw_parts if _clean_location_text(part)]


def _canonical_location_part(value: object) -> str:
    text = _clean_location_text(value)
    if not text:
        return ""
    key = _normalize_key(text)
    if key in IGNORED_LOCATION_TOKENS:
        return ""
    if key in LOCATION_DISPLAY_ALIASES:
        return LOCATION_DISPLAY_ALIASES[key]
    compact_key = _normalize_key(_remove_location_qualifiers(text))
    if compact_key in LOCATION_DISPLAY_ALIASES:
        return LOCATION_DISPLAY_ALIASES[compact_key]
    return text


def _remove_location_qualifiers(value: str) -> str:
    key = _normalize_key(value)
    ignored_phrases = {*GENERIC_LOCATION_WORDS, *IGNORED_LOCATION_TOKENS}
    for phrase in sorted(ignored_phrases, key=len, reverse=True):
        key = re.sub(rf"\b{re.escape(phrase)}\b", " ", key)
    return re.sub(r"\s+", " ", key).strip()


def _normalize_key(value: object) -> str:
    text = _clean_location_text(value).lower()
    text = _strip_accents(text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))

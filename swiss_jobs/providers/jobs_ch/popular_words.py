from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_INPUT_PATH = "runtime/jobs_ch/config-info/jobs_ch.sqlite"
DEFAULT_TOP_N = 20
FALLBACK_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "these",
    "this",
    "to",
    "was",
    "we",
    "with",
    "you",
    "your",
    "und",
    "der",
    "die",
    "das",
    "ein",
    "eine",
    "im",
    "mit",
    "von",
    "zu",
}


def normalize_token(value: str) -> str:
    """Normalize token for stopword matching and counting."""
    token = value.lower().strip()
    token = re.sub(r"[^\w]+", "", token, flags=re.UNICODE)
    return token


def split_and_normalize_terms(values: list[str]) -> set[str]:
    """Split raw stopword strings by comma/space and normalize."""
    out: set[str] = set()
    for raw in values:
        for chunk in re.split(r"[,\s]+", raw.strip()):
            term = normalize_token(chunk)
            if term:
                out.add(term)
    return out


def ensure_base_stopwords() -> set[str]:
    """Load NLTK English stopwords with fallback for SSL/network issues."""
    try:
        import nltk
        from nltk.corpus import stopwords
    except ModuleNotFoundError:
        print("[warn] nltk is not installed; using built-in fallback stopwords.")
        return set(FALLBACK_STOPWORDS)

    try:
        words = set(stopwords.words("english"))
        return split_and_normalize_terms(list(words))
    except LookupError:
        try:
            nltk.download("stopwords", quiet=True)
            words = set(stopwords.words("english"))
            return split_and_normalize_terms(list(words))
        except Exception:
            print(
                "[warn] Could not download NLTK stopwords (SSL/network issue). "
                "Using built-in fallback stopwords."
            )
            return set(FALLBACK_STOPWORDS)


def load_stopwords_file(path: str) -> set[str]:
    """Load custom stopwords from .txt or .json file."""
    file_path = Path(path)
    if not file_path.exists():
        raise ValueError(f"Stopwords file not found: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()

    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in stopwords file '{file_path}': {exc}") from exc
        if isinstance(payload, list):
            return split_and_normalize_terms([str(x) for x in payload])
        if isinstance(payload, dict):
            raw = payload.get("stopwords")
            if isinstance(raw, list):
                return split_and_normalize_terms([str(x) for x in raw])
        raise ValueError("Stopwords JSON must be list or object with key 'stopwords'")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return split_and_normalize_terms(lines)


def build_stopwords(extra_terms: list[str], stopwords_file: str) -> set[str]:
    """Build final stopword set: NLTK base + optional custom terms."""
    stop_words = set(ensure_base_stopwords())
    if stopwords_file:
        stop_words.update(load_stopwords_file(stopwords_file))
    if extra_terms:
        stop_words.update(split_and_normalize_terms(extra_terms))
    return stop_words


def load_jobs(path: str) -> list[dict[str, Any]]:
    """Load vacancies from jobs.ch JSON payload or SQLite database."""
    input_path = Path(path)
    if not input_path.exists():
        raise ValueError(f"Input file not found: {input_path}")

    if input_path.suffix.lower() in {".sqlite", ".db"}:
        return load_jobs_from_database(input_path)

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in '{input_path}': {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Cannot read '{input_path}': {exc}") from exc

    jobs: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        raw_jobs = payload.get("jobs")
        if isinstance(raw_jobs, list):
            jobs = [job for job in raw_jobs if isinstance(job, dict)]
    elif isinstance(payload, list):
        jobs = [job for job in payload if isinstance(job, dict)]

    if not jobs:
        raise ValueError("No jobs found in input JSON.")
    return jobs


def load_jobs_from_database(path: Path) -> list[dict[str, Any]]:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(path)
        rows = connection.execute(
            """
            SELECT vacancy_id, title, description_text, description_html
            FROM vacancies
            ORDER BY last_seen_at DESC, vacancy_id
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(f"Cannot read SQLite database '{path}': {exc}") from exc
    finally:
        try:
            if connection is not None:
                connection.close()
        except Exception:
            pass

    jobs = [
        {
            "id": row[0],
            "title": row[1],
            "description_text": row[2],
            "description_html": row[3],
        }
        for row in rows
    ]
    if not jobs:
        raise ValueError("No vacancies found in SQLite database.")
    return jobs


def extract_job_text(job: dict[str, Any]) -> str:
    """Build text source for analysis from one vacancy."""
    parts = [
        str(job.get("title") or ""),
        str(job.get("description_text") or ""),
        str(job.get("description_html") or ""),
    ]
    text = " ".join(part for part in parts if part).strip()
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def normalize_and_tokenize(text: str, stop_words: set[str]) -> list[str]:
    """Lowercase, remove punctuation, tokenize, remove stop words."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    tokens = re.split(r"\s+", text.strip())

    filtered: list[str] = []
    for token in tokens:
        norm = normalize_token(token)
        if not norm:
            continue
        if norm in stop_words:
            continue
        if norm.isdigit():
            continue
        filtered.append(norm)
    return filtered


def compute_word_frequencies(jobs: list[dict[str, Any]], stop_words: set[str]) -> Counter[str]:
    """Count frequencies of words across all vacancy descriptions."""
    counter: Counter[str] = Counter()
    for job in jobs:
        text = extract_job_text(job)
        if not text:
            continue
        tokens = normalize_and_tokenize(text, stop_words)
        counter.update(tokens)
    return counter


def get_top_words(counter: Counter[str], top_n: int = DEFAULT_TOP_N) -> list[tuple[str, int]]:
    """Return sorted top-N list of (word, count)."""
    return counter.most_common(top_n)


def analyze_popular_words(
    input_path: str,
    top_n: int = DEFAULT_TOP_N,
    extra_stopwords: list[str] | None = None,
    stopwords_file: str = "",
) -> list[tuple[str, int]]:
    """End-to-end analysis function."""
    jobs = load_jobs(input_path)
    stop_words = build_stopwords(extra_stopwords or [], stopwords_file)
    counter = compute_word_frequencies(jobs, stop_words)
    return get_top_words(counter, top_n=top_n)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze most frequent words in jobs.ch vacancy descriptions."
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT_PATH,
        help=f"Input JSON or SQLite file (default: {DEFAULT_INPUT_PATH})",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Number of top words to output (default: {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--stopwords-file",
        default="",
        help="Optional path to custom stopwords file (.txt or .json).",
    )
    parser.add_argument(
        "--extra-stopwords",
        action="append",
        default=[],
        help="Additional stopwords (comma or space separated). Can be repeated.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.top <= 0:
        print("--top must be > 0")
        return 2

    try:
        result = analyze_popular_words(
            args.input,
            top_n=args.top,
            extra_stopwords=args.extra_stopwords,
            stopwords_file=args.stopwords_file,
        )
    except ValueError as exc:
        print(f"[error] {exc}")
        return 2

    print(f"Top-{args.top} most frequent words:\n")
    for word, count in result:
        print(f"{word}: {count}")

    print("\nAs sorted list (word, count):")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

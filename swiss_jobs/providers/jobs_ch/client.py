from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Sequence

import requests

from swiss_jobs.core.models import ClientConfig, QuerySpec, VacancyFull

from .detail import apply_detail_payload, extract_detail_payload
from .extractors import ParseError, extract_js_object, get_results_bucket, parse_jobs_from_bucket

BASE_URL = "https://www.jobs.ch"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}


class JobsChHttpClient:
    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or HEADERS)
        self.timeout = timeout

    def search(
        self,
        config: ClientConfig,
        queries: Sequence[QuerySpec],
    ) -> tuple[list[VacancyFull], list[str], int]:
        warnings: list[str] = []
        all_jobs: list[VacancyFull] = []
        successful_queries = 0

        with requests.Session() as session:
            session.headers.update(self.headers)
            for query in queries:
                if config.show_progress:
                    print(f"[progress] start {query.label}", file=sys.stderr)
                try:
                    all_jobs.extend(
                        self._fetch_query(
                            session=session,
                            mode=config.mode,
                            term=query.term,
                            location=query.location,
                            max_pages=config.max_pages,
                            show_progress=config.show_progress,
                            query_label=query.label,
                        )
                    )
                    successful_queries += 1
                except (requests.RequestException, ParseError) as exc:
                    warnings.append(f"{query.label} failed: {exc}")

        return _dedupe_vacancies(all_jobs), warnings, successful_queries

    def enrich_vacancies(
        self,
        vacancies: Sequence[VacancyFull],
        *,
        detail_limit: int | None,
        detail_workers: int,
        show_progress: bool,
    ) -> tuple[int, int]:
        if not vacancies:
            return 0, 0

        limit = len(vacancies) if not detail_limit else min(detail_limit, len(vacancies))
        for idx, vacancy in enumerate(vacancies):
            vacancy.detail_schema_skipped = idx >= limit

        if limit == 0:
            return 0, 0

        if show_progress:
            print(
                f"[progress] fetching detail schema for {limit} vacancies with {detail_workers} workers...",
                file=sys.stderr,
            )

        def fetch_payload(url: str) -> tuple[dict[str, Any] | None, str | None]:
            try:
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                return extract_detail_payload(response.text), None
            except Exception as exc:  # pragma: no cover
                return None, str(exc)

        enriched = 0
        if detail_workers <= 1:
            for done, idx in enumerate(range(limit), start=1):
                payload, error = fetch_payload(vacancies[idx].url)
                apply_detail_payload(vacancies[idx], payload, error)
                if payload:
                    enriched += 1
                if show_progress and (done == limit or done % 10 == 0):
                    print(f"[progress] detail fetched: {done}/{limit}", file=sys.stderr)
            return limit, enriched

        with ThreadPoolExecutor(max_workers=detail_workers) as executor:
            future_to_idx = {
                executor.submit(fetch_payload, vacancies[idx].url): idx
                for idx in range(limit)
            }
            done = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                done += 1
                try:
                    payload, error = future.result()
                except Exception as exc:  # pragma: no cover
                    payload, error = None, str(exc)
                apply_detail_payload(vacancies[idx], payload, error)
                if payload:
                    enriched += 1
                if show_progress and (done == limit or done % 10 == 0):
                    print(f"[progress] detail fetched: {done}/{limit}", file=sys.stderr)
        return limit, enriched

    def _fetch_query(
        self,
        *,
        session: requests.Session,
        mode: str,
        term: str,
        location: str,
        max_pages: int,
        show_progress: bool,
        query_label: str,
    ) -> list[VacancyFull]:
        all_jobs: list[VacancyFull] = []
        endpoint = "/en/new-vacancies/" if mode == "new" else "/en/vacancies/"
        page = 1
        planned_pages: int | None = max_pages if max_pages > 0 else None

        while True:
            params: dict[str, Any] = {}
            if mode == "search":
                if term:
                    params["term"] = term
                if location:
                    params["location"] = location
            if page > 1:
                params["page"] = page

            try:
                init_state = self._get_init_state(
                    session,
                    f"{self.base_url}{endpoint}",
                    params,
                )
            except (requests.RequestException, ParseError) as exc:
                if all_jobs:
                    if show_progress:
                        print(
                            f"[warn] {query_label}: page {page} failed ({exc}); keeping partial results",
                            file=sys.stderr,
                        )
                    break
                raise

            bucket = get_results_bucket(init_state, mode=mode)
            jobs = parse_jobs_from_bucket(bucket, base_url=self.base_url)
            if not jobs:
                break

            all_jobs.extend(jobs)
            if planned_pages is None:
                meta = bucket.get("meta", {})
                num_pages = meta.get("numPages")
                planned_pages = num_pages if isinstance(num_pages, int) and num_pages > 0 else page

            if show_progress:
                pages_hint = planned_pages if planned_pages is not None else "?"
                print(
                    f"[progress] {query_label}: page {page}/{pages_hint}, got {len(jobs)}, total {len(all_jobs)}",
                    file=sys.stderr,
                )

            if planned_pages is not None and page >= planned_pages:
                break
            page += 1

        return _dedupe_vacancies(all_jobs)

    def _get_init_state(
        self,
        session: requests.Session,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        response = session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return extract_js_object(response.text, "__INIT__ =")


def _dedupe_vacancies(vacancies: Sequence[VacancyFull]) -> list[VacancyFull]:
    seen: set[str] = set()
    result: list[VacancyFull] = []
    for vacancy in vacancies:
        if vacancy.id in seen:
            continue
        seen.add(vacancy.id)
        result.append(vacancy)
    return result

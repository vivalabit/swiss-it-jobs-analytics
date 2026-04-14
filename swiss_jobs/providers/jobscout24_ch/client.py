from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Sequence
from urllib.parse import quote

import requests

from swiss_jobs.core.models import ClientConfig, QuerySpec, VacancyFull

from .detail import apply_detail_payload
from .extractors import ParseError, extract_detail_payload, parse_jobs_from_search_page

BASE_URL = "https://www.jobscout24.ch"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}


class JobScout24ChHttpClient:
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
        self._search_cookies: requests.cookies.RequestsCookieJar | None = None

    def search(
        self,
        config: ClientConfig,
        queries: Sequence[QuerySpec],
    ) -> tuple[list[VacancyFull], list[str], int]:
        warnings: list[str] = []
        all_jobs: list[VacancyFull] = []
        successful_queries = 0

        with self._new_session() as session:
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
            self._search_cookies = session.cookies.copy()

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
                f"[progress] fetching JobScout24 detail pages for {limit} vacancies with {detail_workers} workers...",
                file=sys.stderr,
            )

        session_local = threading.local()

        def get_session() -> requests.Session:
            session = getattr(session_local, "session", None)
            if session is None:
                session = self._new_session()
                session_local.session = session
            return session

        def fetch_payload(vacancy: VacancyFull) -> tuple[dict[str, Any] | None, str | None]:
            try:
                session = get_session()
                return self._fetch_detail_payload(session, vacancy), None
            except Exception as exc:  # pragma: no cover
                return None, str(exc)

        enriched = 0
        if detail_workers <= 1:
            for done, idx in enumerate(range(limit), start=1):
                payload, error = fetch_payload(vacancies[idx])
                apply_detail_payload(vacancies[idx], payload, error)
                if payload:
                    enriched += 1
                if show_progress and (done == limit or done % 10 == 0):
                    print(f"[progress] detail fetched: {done}/{limit}", file=sys.stderr)
            return limit, enriched

        with ThreadPoolExecutor(max_workers=detail_workers) as executor:
            future_to_idx = {
                executor.submit(fetch_payload, vacancies[idx]): idx
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
        page = 1
        planned_pages: int | None = max_pages if max_pages > 0 else None

        while True:
            url = self._build_search_url(mode=mode, term=term, location=location)
            params = {"p": page} if page > 1 else None

            try:
                response = session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
            except requests.RequestException as exc:
                if all_jobs:
                    if show_progress:
                        print(
                            f"[warn] {query_label}: page {page} failed ({exc}); keeping partial results",
                            file=sys.stderr,
                        )
                    break
                raise

            jobs, discovered_pages = parse_jobs_from_search_page(response.text, base_url=self.base_url)
            for job in jobs:
                job.raw.setdefault("search_url", response.url)
                if params:
                    job.raw.setdefault("search_params", dict(params))
            if location:
                jobs = [job for job in jobs if _matches_location(job.place, location)]
            if not jobs:
                break

            all_jobs.extend(jobs)
            if planned_pages is None and discovered_pages:
                planned_pages = discovered_pages

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

    def _build_search_url(self, *, mode: str, term: str, location: str) -> str:
        if mode == "new":
            return f"{self.base_url}/en/jobs/"

        parts = [f"{self.base_url}/en/jobs"]
        if term:
            parts.append(quote(term.strip(), safe=""))
        return "/".join(parts) + "/"

    def _fetch_detail_payload(
        self,
        session: requests.Session,
        vacancy: VacancyFull,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        headers = self._detail_headers(vacancy)
        for attempt in range(3):
            try:
                response = session.get(vacancy.url, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                payload = extract_detail_payload(response.text)
                if attempt > 0 and vacancy.detail_schema_error:
                    vacancy.detail_schema_error = None
                return payload
            except requests.HTTPError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in {403, 429, 500, 502, 503, 504} or attempt == 2:
                    break
                time.sleep(0.75 * (attempt + 1))
            except requests.RequestException as exc:
                last_error = exc
                if attempt == 2:
                    break
                time.sleep(0.5 * (attempt + 1))

        if last_error is None:  # pragma: no cover
            raise RuntimeError(f"Unknown detail fetch error for {vacancy.url}")
        raise last_error

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self.headers)
        if self._search_cookies is not None:
            session.cookies.update(self._search_cookies)
        return session

    def _detail_headers(self, vacancy: VacancyFull) -> dict[str, str] | None:
        search_url = vacancy.raw.get("search_url")
        if isinstance(search_url, str) and search_url.strip():
            return {"Referer": search_url.strip()}
        return None


def _dedupe_vacancies(vacancies: Sequence[VacancyFull]) -> list[VacancyFull]:
    seen: set[str] = set()
    result: list[VacancyFull] = []
    for vacancy in vacancies:
        if vacancy.id in seen:
            continue
        seen.add(vacancy.id)
        result.append(vacancy)
    return result


def _matches_location(place: str, location: str) -> bool:
    normalized_place = _normalize_token(place)
    normalized_location = _normalize_token(location)
    if not normalized_location:
        return True
    return normalized_location in normalized_place


def _normalize_token(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())

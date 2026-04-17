from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Sequence

import requests

from swiss_jobs.core.models import ClientConfig, QuerySpec, VacancyFull

from .detail import apply_detail_payload
from .extractors import ParseError, extract_detail_payload, parse_jobs_from_feed

BASE_URL = "https://swissdevjobs.ch"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}


class SwissDevJobsChHttpClient:
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

        try:
            with self._new_session() as session:
                feed_payload = self._fetch_jobs_feed(session)
                for query in queries:
                    if config.show_progress:
                        print(f"[progress] start {query.label}", file=sys.stderr)
                    jobs, total_pages = parse_jobs_from_feed(
                        feed_payload,
                        base_url=self.base_url,
                        mode=config.mode,
                        term=query.term,
                        location=query.location,
                        max_pages=config.max_pages,
                    )
                    for job in jobs:
                        job.raw.setdefault("search_url", self._build_search_url(mode=config.mode, query=query))
                        job.raw.setdefault(
                            "search_params",
                            {
                                "mode": config.mode,
                                "term": query.term,
                                "location": query.location,
                            },
                        )
                    if config.show_progress:
                        print(
                            (
                                f"[progress] {query.label}: feed pages {total_pages}, "
                                f"got {len(jobs)}, total {len(all_jobs) + len(jobs)}"
                            ),
                            file=sys.stderr,
                        )
                    all_jobs.extend(jobs)
                    successful_queries += 1
        except (requests.RequestException, ValueError, ParseError) as exc:
            for query in queries:
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
                (
                    "[progress] fetching swissdevjobs detail pages "
                    f"for {limit} vacancies with {detail_workers} workers..."
                ),
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

    def _fetch_jobs_feed(self, session: requests.Session) -> list[dict[str, Any]]:
        response = session.get(f"{self.base_url}/api/jobsLight", timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ParseError("SwissDevJobs jobsLight API did not return a list")
        return [dict(item) for item in payload if isinstance(item, dict)]

    def _build_search_url(self, *, mode: str, query: QuerySpec) -> str:
        if mode == "new":
            return f"{self.base_url}/"
        if query.term and query.location:
            return f"{self.base_url}/jobs/{query.term}/{query.location}"
        if query.term:
            return f"{self.base_url}/jobs/{query.term}/all"
        return f"{self.base_url}/"

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
                return extract_detail_payload(response.text, page_url=vacancy.url)
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

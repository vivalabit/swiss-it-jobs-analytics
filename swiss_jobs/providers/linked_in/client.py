from __future__ import annotations

import os
import random
import sys
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

import requests

from swiss_jobs.core.models import ClientConfig, QuerySpec, VacancyFull

from .detail import apply_detail_payload
from .extractors import ParseError, extract_detail_payload, parse_jobs_from_search_page

BASE_URL = "https://www.linkedin.com"
DEFAULT_SWITZERLAND_GEO_ID = "106693272"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}


class LinkedInHttpClient:
    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        headers: dict[str, str] | None = None,
        timeout: int = 45,
        default_max_pages: int = 1,
        env_proxy_names: Sequence[str] = ("SWISS_JOBS_LINKEDIN_PROXY", "LINKEDIN_PROXY"),
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or HEADERS)
        self.timeout = timeout
        self.default_max_pages = default_max_pages
        self.env_proxy_names = tuple(env_proxy_names)
        self._base_cookies: requests.cookies.RequestsCookieJar | None = None
        self._base_cookies_file: str | None = None
        self._search_cookies: requests.cookies.RequestsCookieJar | None = None
        self._active_proxies: dict[str, str] | None = None

    def search(
        self,
        config: ClientConfig,
        queries: Sequence[QuerySpec],
    ) -> tuple[list[VacancyFull], list[str], int]:
        warnings: list[str] = []
        all_jobs: list[VacancyFull] = []
        successful_queries = 0

        self.configure_cookies(
            cookies_file=config.cookies_file,
            show_progress=config.show_progress,
        )
        proxies = self._resolve_proxies(config)
        self._active_proxies = proxies

        with self._new_session(proxies=proxies) as session:
            for idx, query in enumerate(queries):
                if idx > 0:
                    self._sleep(
                        config.request_delay_min_seconds,
                        config.request_delay_max_seconds,
                        show_progress=config.show_progress,
                    )
                if config.show_progress:
                    print(f"[progress] start {query.label}", file=sys.stderr)
                try:
                    jobs = self._fetch_query(
                        session=session,
                        mode=config.mode,
                        term=query.term,
                        location=query.location,
                        max_pages=config.max_pages,
                        delay_min=config.request_delay_min_seconds,
                        delay_max=config.request_delay_max_seconds,
                        show_progress=config.show_progress,
                        query_label=query.label,
                    )
                    all_jobs.extend(jobs)
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
                f"[progress] fetching LinkedIn detail pages slowly for {limit} vacancies...",
                file=sys.stderr,
            )

        enriched = 0
        with self._new_session(proxies=self._active_proxies) as session:
            for idx in range(limit):
                vacancy = vacancies[idx]
                try:
                    response = session.get(
                        vacancy.url,
                        headers=self._detail_headers(vacancy),
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    payload = extract_detail_payload(response.text)
                    apply_detail_payload(vacancy, payload, None)
                    if payload:
                        enriched += 1
                except Exception as exc:  # pragma: no cover
                    apply_detail_payload(vacancy, None, str(exc))

                if show_progress and (idx + 1 == limit or (idx + 1) % 5 == 0):
                    print(f"[progress] detail fetched: {idx + 1}/{limit}", file=sys.stderr)
                if idx + 1 < limit:
                    self._sleep(4.0, 9.0, show_progress=show_progress)
        return limit, enriched

    def _fetch_query(
        self,
        *,
        session: requests.Session,
        mode: str,
        term: str,
        location: str,
        max_pages: int,
        delay_min: float,
        delay_max: float,
        show_progress: bool,
        query_label: str,
    ) -> list[VacancyFull]:
        all_jobs: list[VacancyFull] = []
        planned_pages = max_pages if max_pages > 0 else self.default_max_pages

        for page in range(1, planned_pages + 1):
            if page > 1:
                self._sleep(delay_min, delay_max, show_progress=show_progress)

            params = self._build_query_params(
                mode=mode,
                term=term,
                location=location,
                page=page,
            )
            response = session.get(
                f"{self.base_url}/jobs/search/",
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()

            jobs = parse_jobs_from_search_page(response.text, base_url=self.base_url)
            if not jobs:
                if _looks_like_authwall(response.text):
                    raise ParseError("LinkedIn returned an authentication or checkpoint page")
                break
            for job in jobs:
                job.raw.setdefault("search_url", response.url)
                job.raw.setdefault("search_params", dict(params))
            all_jobs.extend(jobs)

            if show_progress:
                print(
                    f"[progress] {query_label}: page {page}/{planned_pages}, got {len(jobs)}, total {len(all_jobs)}",
                    file=sys.stderr,
                )

        return _dedupe_vacancies(all_jobs)

    def _build_query_params(
        self,
        *,
        mode: str,
        term: str,
        location: str,
        page: int,
    ) -> dict[str, str]:
        params: dict[str, str] = {
            "origin": "JOB_SEARCH_PAGE_JOB_FILTER",
            "sortBy": "DD",
        }
        clean_location = location.strip() or "Switzerland"
        params["location"] = clean_location
        if clean_location.casefold() == "switzerland":
            params["geoId"] = DEFAULT_SWITZERLAND_GEO_ID
        if term.strip():
            params["keywords"] = term.strip()
        if mode == "new":
            params["f_TPR"] = "r86400"
        if page > 1:
            params["start"] = str((page - 1) * 25)
        return params

    def _new_session(self, *, proxies: dict[str, str] | None) -> requests.Session:
        session = requests.Session()
        session.headers.update(self.headers)
        if proxies:
            session.proxies.update(proxies)
        if self._base_cookies is not None:
            session.cookies.update(self._base_cookies)
        if self._search_cookies is not None:
            session.cookies.update(self._search_cookies)
        return session

    def configure_cookies(
        self,
        *,
        cookies_file: str | None,
        show_progress: bool,
    ) -> None:
        normalized = cookies_file.strip() if isinstance(cookies_file, str) else ""
        if not normalized:
            self._base_cookies = None
            self._base_cookies_file = None
            return
        if normalized == self._base_cookies_file and self._base_cookies is not None:
            return

        cookie_jar = MozillaCookieJar(normalized)
        cookie_jar.load(ignore_discard=True, ignore_expires=True)

        cookies = requests.cookies.RequestsCookieJar()
        loaded = 0
        for cookie in cookie_jar:
            cookies.set_cookie(cookie)
            loaded += 1

        self._base_cookies = cookies
        self._base_cookies_file = normalized

        if show_progress:
            print(f"[progress] loaded {loaded} LinkedIn cookies", file=sys.stderr)

    def _resolve_proxies(self, config: ClientConfig) -> dict[str, str] | None:
        raw_proxy = config.proxy_url or self._read_proxy_file(config.proxy_file) or self._read_env_proxy()
        if not raw_proxy:
            return None
        proxy_url = _normalize_proxy_url(raw_proxy)
        return {"http": proxy_url, "https": proxy_url}

    def _read_env_proxy(self) -> str:
        for name in self.env_proxy_names:
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return ""

    def _read_proxy_file(self, proxy_file: str | None) -> str:
        if not proxy_file:
            return ""
        try:
            return Path(proxy_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _detail_headers(self, vacancy: VacancyFull) -> dict[str, str] | None:
        search_url = vacancy.raw.get("search_url")
        if isinstance(search_url, str) and search_url.strip():
            return {"Referer": search_url.strip()}
        return None

    def _sleep(self, minimum: float, maximum: float, *, show_progress: bool) -> None:
        upper = max(minimum, maximum)
        if upper <= 0:
            return
        duration = random.uniform(minimum, upper)
        if show_progress:
            print(f"[progress] LinkedIn throttle sleep {duration:.1f}s", file=sys.stderr)
        time.sleep(duration)


def _normalize_proxy_url(raw_value: str) -> str:
    value = raw_value.strip()
    if "://" in value:
        return value

    parts = value.split(":", 3)
    if len(parts) == 4:
        host, port, username, password = parts
        return f"http://{quote(username)}:{quote(password)}@{host}:{port}"
    if len(parts) == 2:
        host, port = parts
        return f"http://{host}:{port}"
    return value


def _dedupe_vacancies(vacancies: Sequence[VacancyFull]) -> list[VacancyFull]:
    seen: set[str] = set()
    result: list[VacancyFull] = []
    for vacancy in vacancies:
        if vacancy.id in seen:
            continue
        seen.add(vacancy.id)
        result.append(vacancy)
    return result


def _looks_like_authwall(page_html: str) -> bool:
    lowered = page_html.casefold()
    markers = (
        "authwall",
        "checkpoint/challenge",
        "uas/login",
        "sign in to linkedin",
        "join linkedin",
    )
    return any(marker in lowered for marker in markers)

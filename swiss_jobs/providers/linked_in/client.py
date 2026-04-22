from __future__ import annotations

import os
import random
import sys
import time
from contextlib import contextmanager
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Iterator, Sequence
from urllib.parse import quote, urlencode

from swiss_jobs.core.models import ClientConfig, QuerySpec, VacancyFull

from .detail import apply_detail_payload
from .extractors import ParseError, extract_detail_payload, parse_jobs_from_search_page

BASE_URL = "https://www.linkedin.com"
DEFAULT_SWITZERLAND_GEO_ID = "106693272"
DEFAULT_SEARCH_DISTANCE = "25.0"
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
        self._base_cookies_file: str | None = None
        self._active_proxy_value: str = ""
        self._browser_cookies: list[dict[str, Any]] = []

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
        proxy_value = self._resolve_proxy_value(config)
        self._active_proxy_value = proxy_value

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
                jobs, query_warnings = self._fetch_query(
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
                warnings.extend(query_warnings)
                successful_queries += 1
            except (ParseError, RuntimeError) as exc:
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
                f"[progress] fetching LinkedIn detail pages slowly for {limit} vacancies...",
                file=sys.stderr,
            )

        enriched = 0
        try:
            with self._browser_context() as context:
                page = context.new_page()
                for idx in range(limit):
                    vacancy = vacancies[idx]
                    try:
                        detail_panel_url = self._build_detail_panel_url(vacancy)
                        rendered_html, final_url = self._goto_and_capture(
                            page,
                            detail_panel_url,
                            wait_selector=(
                                ".jobs-description__content, .jobs-box__html-content, "
                                ".jobs-unified-top-card__job-title, h1"
                            ),
                            scroll_results=False,
                            scroll_detail=True,
                            click_show_more=True,
                            show_progress=show_progress,
                            progress_label="LinkedIn detail panel",
                        )
                        if not rendered_html:
                            raise RuntimeError("LinkedIn detail browser render returned empty HTML")
                        if _looks_like_authwall(rendered_html):
                            raise ParseError("LinkedIn returned an authentication or checkpoint page")
                        payload = extract_detail_payload(rendered_html)
                        if final_url:
                            payload["detail_panel_url"] = final_url
                        apply_detail_payload(vacancy, payload, None)
                        if _payload_has_detail_data(payload):
                            enriched += 1
                    except Exception as exc:  # pragma: no cover
                        apply_detail_payload(vacancy, None, str(exc))

                    if show_progress and (idx + 1 == limit or (idx + 1) % 5 == 0):
                        print(f"[progress] detail fetched: {idx + 1}/{limit}", file=sys.stderr)
                    if idx + 1 < limit:
                        self._sleep(6.0, 12.0, show_progress=show_progress)
        except Exception as exc:  # pragma: no cover
            for idx in range(limit):
                if not vacancies[idx].detail_schema_error:
                    apply_detail_payload(vacancies[idx], None, str(exc))
        return limit, enriched

    def _fetch_query(
        self,
        *,
        mode: str,
        term: str,
        location: str,
        max_pages: int,
        delay_min: float,
        delay_max: float,
        show_progress: bool,
        query_label: str,
    ) -> tuple[list[VacancyFull], list[str]]:
        all_jobs: list[VacancyFull] = []
        warnings: list[str] = []
        planned_pages = max_pages if max_pages > 0 else self.default_max_pages

        with self._browser_context() as context:
            browser_page = context.new_page()
            for page in range(1, planned_pages + 1):
                if page > 1:
                    self._sleep(delay_min, delay_max, show_progress=show_progress)

                params = self._build_query_params(
                    mode=mode,
                    term=term,
                    location=location,
                    page=page,
                )
                search_url = f"{self.base_url}/jobs/search/?{urlencode(params)}"
                rendered_html, rendered_url = self._goto_and_capture(
                    browser_page,
                    search_url,
                    wait_selector="div.job-card-container, li.jobs-search-results__list-item, a[href*='/jobs/']",
                    scroll_results=True,
                    scroll_detail=False,
                    click_show_more=False,
                    show_progress=show_progress,
                    progress_label="LinkedIn search page",
                )

                if _looks_like_authwall(rendered_html):
                    raise ParseError("LinkedIn returned an authentication or checkpoint page")

                jobs = parse_jobs_from_search_page(rendered_html, base_url=self.base_url)
                if not jobs:
                    warning = (
                        f"{query_label}: no parseable LinkedIn job cards on page {page} "
                        f"at {rendered_url or search_url}"
                    )
                    warnings.append(warning)
                    if show_progress:
                        print(f"[warn] {warning}", file=sys.stderr)
                    break

                for job in jobs:
                    self._attach_search_context(job, search_url=rendered_url or search_url, params=params)
                all_jobs.extend(jobs)

                if show_progress:
                    print(
                        f"[progress] {query_label}: page {page}/{planned_pages}, got {len(jobs)}, total {len(all_jobs)}",
                        file=sys.stderr,
                    )

        return _dedupe_vacancies(all_jobs), warnings

    def _attach_search_context(
        self,
        vacancy: VacancyFull,
        *,
        search_url: str,
        params: dict[str, str],
    ) -> None:
        vacancy.raw.setdefault("search_url", search_url)
        vacancy.raw.setdefault("search_params", dict(params))
        vacancy.raw["detail_panel_url"] = self._build_detail_panel_url(vacancy)

    def _build_query_params(
        self,
        *,
        mode: str,
        term: str,
        location: str,
        page: int,
    ) -> dict[str, str]:
        params: dict[str, str] = {
            "distance": DEFAULT_SEARCH_DISTANCE,
            "geoId": DEFAULT_SWITZERLAND_GEO_ID,
            "origin": "JOBS_HOME_KEYWORD_HISTORY",
        }
        clean_location = location.strip() or "Switzerland"
        if clean_location and not _looks_like_swiss_location(clean_location):
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

    def _build_detail_panel_url(self, vacancy: VacancyFull) -> str:
        linkedin_job_id = str(vacancy.raw.get("linkedinJobId") or "").strip()
        if not linkedin_job_id and vacancy.id.startswith("linkedin:"):
            linkedin_job_id = vacancy.id.split(":", 1)[1]

        params = {}
        raw_params = vacancy.raw.get("search_params")
        if isinstance(raw_params, dict):
            params.update({str(key): str(value) for key, value in raw_params.items() if value is not None})
        params.setdefault("distance", DEFAULT_SEARCH_DISTANCE)
        params.setdefault("geoId", DEFAULT_SWITZERLAND_GEO_ID)
        params.setdefault("origin", "JOBS_HOME_KEYWORD_HISTORY")
        if linkedin_job_id:
            params["currentJobId"] = linkedin_job_id
        return f"{self.base_url}/jobs/search/?{urlencode(params)}"

    def configure_cookies(
        self,
        *,
        cookies_file: str | None,
        show_progress: bool,
    ) -> None:
        normalized = cookies_file.strip() if isinstance(cookies_file, str) else ""
        if not normalized:
            self._base_cookies_file = None
            self._browser_cookies = []
            return
        if normalized == self._base_cookies_file and self._browser_cookies:
            return

        cookie_jar = MozillaCookieJar(normalized)
        cookie_jar.load(ignore_discard=True, ignore_expires=True)

        browser_cookies: list[dict[str, Any]] = []
        loaded = 0
        for cookie in cookie_jar:
            browser_cookie: dict[str, Any] = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path or "/",
                "secure": bool(cookie.secure),
                "httpOnly": bool(
                    getattr(cookie, "_rest", {}).get("HttpOnly")
                    or getattr(cookie, "_rest", {}).get("httponly")
                ),
            }
            if cookie.expires is not None:
                browser_cookie["expires"] = cookie.expires
            browser_cookies.append(browser_cookie)
            loaded += 1

        self._base_cookies_file = normalized
        self._browser_cookies = browser_cookies

        if show_progress:
            print(f"[progress] loaded {loaded} LinkedIn cookies", file=sys.stderr)

    @contextmanager
    def _browser_context(
        self,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Any]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(f"Playwright is unavailable; install playwright browsers: {exc}") from exc

        browser = None
        context = None
        with sync_playwright() as playwright:
            launch_kwargs: dict[str, Any] = {"headless": True}
            browser_proxy = _build_browser_proxy(self._active_proxy_value)
            if browser_proxy:
                launch_kwargs["proxy"] = browser_proxy

            browser = playwright.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                user_agent=self.headers.get("User-Agent"),
                locale="ru-RU",
                timezone_id="Europe/Zurich",
                viewport={"width": 1440, "height": 1200},
                extra_http_headers={
                    "Accept-Language": self.headers.get("Accept-Language", "en-US,en;q=0.9"),
                    **(extra_headers or {}),
                },
            )
            if self._browser_cookies:
                context.add_cookies(self._browser_cookies)
            try:
                yield context
            finally:
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()

    def _goto_and_capture(
        self,
        page: Any,
        url: str,
        *,
        wait_selector: str,
        scroll_results: bool,
        scroll_detail: bool,
        click_show_more: bool,
        show_progress: bool,
        progress_label: str,
    ) -> tuple[str, str]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        except ImportError as exc:
            raise RuntimeError(f"Playwright is unavailable; install playwright browsers: {exc}") from exc

        if show_progress:
            print(f"[progress] rendering {progress_label} with Chromium", file=sys.stderr)

        page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
        try:
            page.wait_for_selector(wait_selector, timeout=20000)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(random.randint(1200, 2600))
        if scroll_results:
            self._scroll_linkedin_results(page)
        if scroll_detail:
            self._scroll_linkedin_detail(page)
        if click_show_more:
            self._click_linkedin_show_more(page)
            self._scroll_linkedin_detail(page)
        page.wait_for_timeout(random.randint(1800, 3200))
        return page.content(), page.url

    def _scroll_linkedin_results(self, page: Any) -> None:
        for _ in range(3):
            page.evaluate(
                """
                () => {
                  const containers = [
                    document.querySelector('.jobs-search-results-list'),
                    document.querySelector('.scaffold-layout__list'),
                    document.querySelector('[aria-label*="Search results"]'),
                    document.scrollingElement
                  ].filter(Boolean);
                  const target = containers[0];
                  target.scrollTop = target.scrollHeight;
                }
                """
            )
            page.wait_for_timeout(1200)

    def _scroll_linkedin_detail(self, page: Any) -> None:
        for _ in range(3):
            page.evaluate(
                """
                () => {
                  const containers = [
                    document.querySelector('.jobs-search__job-details--container'),
                    document.querySelector('.jobs-details'),
                    document.querySelector('.scaffold-layout__detail'),
                    document.scrollingElement
                  ].filter(Boolean);
                  const target = containers[0];
                  target.scrollTop = Math.min(target.scrollHeight, target.scrollTop + 900);
                }
                """
            )
            page.wait_for_timeout(1000)

    def _click_linkedin_show_more(self, page: Any) -> None:
        for text in ("Show more", "See more", "Показать ещё", "Показать еще", "Ещё", "Еще"):
            try:
                locator = page.get_by_text(text, exact=False).first
                if locator.count() > 0 and locator.is_visible(timeout=800):
                    locator.click(timeout=1500)
                    page.wait_for_timeout(1000)
                    return
            except Exception:
                continue
        for selector in (
            "button.jobs-description__footer-button",
            "button[aria-label*='Show more']",
            "button[aria-label*='Показать']",
            ".jobs-description button",
        ):
            try:
                locator = page.locator(selector).first
                if locator.count() > 0 and locator.is_visible(timeout=800):
                    locator.click(timeout=1500)
                    page.wait_for_timeout(1000)
                    return
            except Exception:
                continue

    def _resolve_proxy_value(self, config: ClientConfig) -> str:
        return config.proxy_url or self._read_proxy_file(config.proxy_file) or self._read_env_proxy()

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


def _build_browser_proxy(raw_value: str) -> dict[str, str] | None:
    value = raw_value.strip()
    if not value:
        return None

    if "://" in value:
        return {"server": value}

    parts = value.split(":", 3)
    if len(parts) == 4:
        host, port, username, password = parts
        return {
            "server": f"http://{host}:{port}",
            "username": username,
            "password": password,
        }
    if len(parts) == 2:
        host, port = parts
        return {"server": f"http://{host}:{port}"}
    return {"server": value}


def _looks_like_swiss_location(value: str) -> bool:
    normalized = value.casefold()
    swiss_markers = (
        "switzerland",
        "swiss",
        "schweiz",
        "suisse",
        "svizzera",
        "zurich",
        "zürich",
        "geneva",
        "genève",
        "lausanne",
        "basel",
        "bern",
        "winterthur",
        "zug",
        "lucerne",
        "st. gallen",
        "st gallen",
    )
    return any(marker in normalized for marker in swiss_markers)


def _dedupe_vacancies(vacancies: Sequence[VacancyFull]) -> list[VacancyFull]:
    seen: set[str] = set()
    result: list[VacancyFull] = []
    for vacancy in vacancies:
        if vacancy.id in seen:
            continue
        seen.add(vacancy.id)
        result.append(vacancy)
    return result


def _payload_has_detail_data(payload: dict[str, Any]) -> bool:
    if payload.get("job_posting_schema"):
        return True
    for key in ("description_text", "description_html"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    detail_attributes = payload.get("detail_attributes")
    if isinstance(detail_attributes, dict) and detail_attributes:
        return True
    return False


def _looks_like_authwall(page_html: str) -> bool:
    lowered = page_html.casefold()
    markers = (
        "authwall",
        "checkpoint/challenge",
        "uas/login",
        "sign in to linkedin",
        "join linkedin",
        "войти или зарегистрироваться",
        "присоединиться к linkedin",
    )
    return any(marker in lowered for marker in markers)

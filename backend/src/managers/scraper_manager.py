from __future__ import annotations

import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import aiohttp

from backend.config import get_app_config, get_settings
from backend.database.connection import async_session_factory
from backend.logging_config import get_logger
from backend.src.managers.database_manager import (
    UNCATEGORIZED_NAME,
    DatabaseManager,
)
from backend.src.managers.session_manager import SessionManager
from backend.src.models import CrawlMode, JobStatus, LogLevel
from backend.src.services.classification_service import get_classification_service
from backend.src.services.content_extractor import ContentExtractor
from backend.src.services.url_resolver import URLResolver

logger = get_logger("scraper_manager")

# JUST A TIP FOR NEXT USAGE WHY NOT USE BART ON THREADS
# ---------------------------------------------------------------------------
# Process-level BART singleton — one instance shared across all threads
# ---------------------------------------------------------------------------
# WHY NOT thread-local:
#   threading.local() creates one BART model per thread. With concurrency=10
#   that is 10 × ~1.6 GB = ~16 GB RAM. The machine runs out of memory.
#
# WHY SHARED IS SAFE:
#   PyTorch releases the GIL during all tensor operations (BLAS/MKL). Threads
#   calling model.predict() on the same model instance run in parallel with
#   no GIL contention. The only serialised part is the initial model load,
#   which is protected by _bart_lock and happens exactly once.
#
# RESULT: 1 × ~1.6 GB regardless of concurrency setting.
# ---------------------------------------------------------------------------
_bart_lock = threading.Lock()
_bart_provider: Any = None
_bart_config_key: str = ""  # detects config changes that require a reload


def _get_thread_classification_service(classification_config: Dict) -> Any:
    """
    Return the process-level BART provider singleton.
    Thread-safe: the lock is held only during the first load.
    Subsequent calls return the cached instance without locking.
    """
    global _bart_provider, _bart_config_key

    # Fast path — already loaded, no lock needed
    config_key = classification_config.get("provider", "none")
    if _bart_provider is not None and _bart_config_key == config_key:
        return _bart_provider

    # Slow path — first load, hold the lock
    with _bart_lock:
        # Re-check inside lock in case another thread loaded it first
        if _bart_provider is not None and _bart_config_key == config_key:
            return _bart_provider

        from backend.src.services.classification.factory import create_provider
        _bart_provider = create_provider(classification_config)
        _bart_config_key = config_key

    return _bart_provider


#---------------------------------------------------------------------------
# THREAD WORKER — runs in ThreadPoolExecutor
def _thread_worker(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry point for each thread. Creates a fresh asyncio event loop,
    runs the full fetch+extract+classify pipeline, returns a plain dict.

    Threads are NOT daemon processes — no restriction on their activities.
    Each thread has its own event loop so aiohttp and asyncio work normally.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(_pipeline(args))
    except Exception as exc:
        return {
            "url": args.get("url", ""),
            "success": False,
            "html": None,
            "content_blocks": None,
            "page_title": None,
            "http_status": None,
            "error": str(exc),
            "labels": [],
            "classified": False,
        }
    finally:
        try:
            # Clean up pending tasks before closing
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        finally:
            loop.close()


async def _pipeline(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full pipeline for one URL:
      fetch (aiohttp) -> wall-detect -> [Playwright if needed] -> extract -> classify

    Wall detection runs after every HTTP fetch. Actions:
      SKIP:     return error result immediately (Cloudflare, CAPTCHA, IP ban, paywall)
      LOGIN     log warning, skip (coordinator handles re-auth between jobs)
      RETRY:    sleep Retry-After seconds, retry the request
      DISMISS:  trigger Playwright to auto-click cookie consent accept button
      NONE:     proceed normally
    """
    url: str = args["url"]
    data_targets: List[str] = args.get("data_targets", ["text"])
    timeout_sec: int = int(args.get("timeout", 30))
    user_agent: str = args.get("user_agent", "WebScraper/1.0")
    max_retries: int = int(args.get("max_retries", 3))
    retry_delay: float = float(args.get("retry_delay", 2.0))
    classify_here: bool = bool(args.get("classify_in_process", True))
    classification_config: Dict = args.get("classification_config") or {}
    js_mode: str = args.get("js_mode", "auto")
    js_threshold: float = float(args.get("js_detection_threshold", 3.0))
    injected_cookies: Dict = args.get("cookies") or {}

    result: Dict[str, Any] = {
        "url": url,
        "success": False,
        "html": None,
        "content_blocks": None,
        "page_title": None,
        "http_status": None,
        "error": None,
        "labels": [],
        "classified": False,
        "wall_type": None,
    }

    from backend.src.services.wall_detector import WallDetector, WallAction

    headers = {"User-Agent": user_agent}
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    html: Optional[str] = None
    response_headers: Dict = {}
    use_playwright = (js_mode == "always")


    #---------------------------------------------------------------------------
    # AIOHTTP FETCH (skipped when js_mode="always")
    if js_mode != "always":
        for attempt in range(max_retries + 1):
            try:
                async with aiohttp.ClientSession(
                    headers=headers,
                    cookies=injected_cookies or None,
                ) as session:
                    async with session.get(url, timeout=timeout) as response:
                        result["http_status"] = response.status
                        response_headers = dict(response.headers)

                        # Collect cookie names for wall detection
                        cookie_names = [
                            c.key for c in session.cookie_jar
                        ]

                        raw_html = ""
                        if response.status == 200:
                            raw_html = await response.text(errors="replace")
                        else:
                            # Read body for wall detection even on error codes
                            try:
                                raw_html = await response.text(errors="replace")
                            except Exception:
                                raw_html = ""

                        # Wall detection
                        wall = WallDetector().detect(
                            status=response.status,
                            headers=response_headers,
                            html=raw_html,
                            final_url=str(response.url),
                            cookie_names=cookie_names,
                        )

                        if wall.wall_type.value != "none":
                            logger.warning(
                                "wall_detected",
                                url=url[:80],
                                wall_type=wall.wall_type.value,
                                action=wall.action.value,
                                signals=wall.signals,
                                confidence=wall.confidence,
                            )
                            result["wall_type"] = wall.wall_type.value

                        if wall.action.value == "skip":
                            result["error"] = (
                                f"Wall blocked ({wall.wall_type.value}): "
                                f"{'; '.join(wall.signals)}"
                            )
                            return result

                        if wall.action.value == "retry":
                            sleep_sec = wall.retry_after_seconds or (
                                retry_delay * (2 ** attempt)
                            )
                            await asyncio.sleep(sleep_sec)
                            continue

                        if wall.action.value == "login":
                            # Thread has no DB/Redis access — log and skip.
                            # The coordinator will handle re-auth via
                            # SessionManager before the next job run.
                            result["error"] = (
                                f"Auth wall ({wall.wall_type.value}) — "
                                f"no valid session. Add credentials in the UI."
                            )
                            return result

                        if wall.action.value == "dismiss":
                            # Cookie consent — try Playwright to click accept.
                            # Fall through to Playwright path below.
                            use_playwright = True

                        if response.status == 200:
                            html = raw_html
                            break

                        if response.status in (301, 302, 303, 307, 308):
                            result["error"] = f"Redirect {response.status}"
                            return result

                        if response.status >= 500 and attempt < max_retries:
                            await asyncio.sleep(retry_delay * (2 ** attempt))
                            continue

                        result["error"] = f"HTTP {response.status}"
                        return result

            except Exception as exc:
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
                result["error"] = str(exc)
                return result

    if html is None and js_mode == "never":
        result["error"] = "No content received"
        return result


    #---------------------------------------------------------------------------
    # FIRST-PASS EXTRACTION (for JS auto-detection)
    first_pass_blocks = None
    if html is not None:
        try:
            extractor = ContentExtractor()
            first_pass_blocks = extractor.extract(
                html, url=url, data_targets=data_targets
            )
        except Exception:
            first_pass_blocks = []


    #---------------------------------------------------------------------------
    # JS AUTO-DETECTION
    if js_mode == "auto" and html is not None and not use_playwright:
        from backend.src.services.js_detector import JSDetector as _JSD
        detector = _JSD(threshold=int(js_threshold))
        detection = detector.detect(
            html,
            content_blocks=first_pass_blocks,
            response_headers={
                k.lower(): v for k, v in response_headers.items()
            },
        )
        if detection.needs_js:
            use_playwright = True
            logger.info(
                "js_rendering_triggered",
                url=url[:80],
                score=detection.score,
                threshold=detection.threshold,
                signals=detection.signals_fired,
            )


    #---------------------------------------------------------------------------
    # PLAYWRIGHT FETCH
    if use_playwright:
        try:
            from playwright.async_api import async_playwright as _pw

            async with _pw() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=user_agent,
                    ignore_https_errors=True,
                )

                # Inject stored cookies into the browser context
                if injected_cookies:
                    from urllib.parse import urlparse as _up
                    _parsed = _up(url)
                    cookie_list = [
                        {
                            "name": k,
                            "value": v,
                            "domain": _parsed.netloc,
                            "path": "/",
                        }
                        for k, v in injected_cookies.items()
                    ]
                    await context.add_cookies(cookie_list)

                page = await context.new_page()
                try:
                    await page.goto(
                        url,
                        timeout=timeout_sec * 1000,
                        wait_until="networkidle",
                    )

                    # Auto-dismiss cookie consent if wall type was COOKIE_CONSENT
                    if result.get("wall_type") == "cookie_consent":
                        for selector in [
                            "button[id*='accept']",
                            "button[class*='accept']",
                            "button[id*='cookie']",
                            "#onetrust-accept-btn-handler",
                            ".cc-allow",
                            "[data-testid='cookie-policy-dialog-accept-button']",
                        ]:
                            try:
                                btn = page.locator(selector).first
                                if await btn.is_visible(timeout=1000):
                                    await btn.click()
                                    await page.wait_for_load_state("networkidle")
                                    break
                            except Exception:
                                continue

                    html = await page.content()
                    result["http_status"] = 200

                    # Run wall detection on Playwright result too
                    pw_wall = WallDetector().detect(
                        status=200,
                        headers={},
                        html=html,
                        final_url=page.url,
                    )
                    if pw_wall.action.value == "skip":
                        result["error"] = (
                            f"Wall persists after Playwright "
                            f"({pw_wall.wall_type.value})"
                        )
                        # Don't return here — fall through to finally
                        # which closes the browser and then we return below.
                        html = None

                except Exception as pw_exc:
                    if html is None:
                        result["error"] = f"Playwright error: {pw_exc}"
                    else:
                        logger.warning(
                            "playwright_fallback_to_aiohttp",
                            url=url[:80],
                            error=str(pw_exc),
                        )
                finally:
                    # Single close point — always runs, never double-closes.
                    # browser.close() also terminates the Chromium subprocess
                    # and releases its memory. This is the ONLY place we close.
                    try:
                        await browser.close()
                    except Exception:
                        pass

                # If wall blocked or error and no html fallback, exit now
                if html is None and result.get("error"):
                    return result

        except ImportError:
            logger.warning(
                "playwright_not_installed",
                url=url[:80],
            )
            if html is None:
                result["error"] = "Playwright not installed and aiohttp got no content"
                return result

    if html is None:
        result["error"] = "No content received"
        return result

    result["html"] = html


    #---------------------------------------------------------------------------
    # FINAL CONTENT EXTRACTION
    try:
        extractor = ContentExtractor()
        if use_playwright or first_pass_blocks is None:
            result["content_blocks"] = extractor.extract(
                html, url=url, data_targets=data_targets
            )
        else:
            result["content_blocks"] = first_pass_blocks
        result["page_title"] = extractor.extract_title(html)
        result["success"] = True
    except Exception as exc:
        result["error"] = f"Extraction error: {exc}"
        return result


    #---------------------------------------------------------------------------
    # CLASSIFICATION (in-thread, optional)
    if classify_here and result["content_blocks"] and classification_config:
        provider_name = classification_config.get("provider", "none")

        if provider_name != "none":
            try:
                provider = _get_thread_classification_service(
                    classification_config
                )

                max_words = int(classification_config.get("max_words", 500))
                title_text = result["page_title"] or ""
                body_parts: List[str] = []
                word_count = 0

                for block in result["content_blocks"]:
                    text = (
                        block.get("content", "")
                        if isinstance(block, dict)
                        else str(block)
                    )
                    words = text.split()
                    remaining = max_words - word_count
                    if remaining <= 0:
                        break
                    body_parts.append(" ".join(words[:remaining]))
                    word_count += min(len(words), remaining)

                full_text = f"{title_text} {' '.join(body_parts)}".strip()

                raw_labels = classification_config.get("candidate_labels", "")
                candidate_labels = (
                    [l.strip() for l in raw_labels.split(",") if l.strip()]
                    if isinstance(raw_labels, str)
                    else list(raw_labels)
                )

                threshold = float(
                    classification_config.get("confidence_threshold", 0.4)
                )

                raw = await provider.classify(
                    text=full_text,
                    candidate_labels=candidate_labels,
                )

                result["labels"] = [
                    label
                    for label, score in zip(raw.labels, raw.scores)
                    if score >= threshold
                ]
                result["classified"] = True

            except Exception as exc:
                logger.warning(
                    "thread_classification_failed",
                    url=url[:80],
                    error=str(exc),
                )
                result["labels"] = []
                result["classified"] = False

    return result


#----------------------------------------------------------------------------------------------------
# SCRAPER MANAGER — coordinator (runs in Celery worker's asyncio event loop)
class ScraperManager:
    """
    Coordinator for web scraping jobs.
    Dispatches URLs to ThreadPoolExecutor workers, handles DB writes,
    link discovery, and stop/pause signalling.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._app_config = get_app_config()
        self._db_manager = DatabaseManager()
        self._session_manager = SessionManager()
        self._url_resolver = URLResolver()
        self._classification_service = get_classification_service()
        self._request_delay = self._settings.scraper_default_delay_between_requests

    def _build_worker_args(self, data_targets: List[str]) -> Dict[str, Any]:
        """Build the args dict passed to every thread worker."""
        classify_in_subprocess = self._app_config.classification_run_in_subprocess

        return {
            "data_targets": data_targets,
            "js_mode": "auto",  # overwritten per-job in run_job
            "js_detection_threshold": self._app_config.js_detection_threshold,
            "timeout": self._settings.scraper_default_timeout,
            "user_agent": self._settings.scraper_user_agent,
            "max_retries": self._settings.scraper_max_retries,
            "retry_delay": float(self._settings.scraper_retry_delay),
            "classify_in_process": classify_in_subprocess,
            "classification_config": (
                self._app_config.classification_config_dict
                if classify_in_subprocess
                else {}
            ),
            # Serialised cookies for this domain populated per-job in run_job()
            # so the thread can inject them without needing Redis access.
            "cookies": {},
        }


    #---------------------------------------------------------------------------
    # PUBLIC ENTRY POINT
    async def run_job(
        self,
        job_id: uuid.UUID,
        stop_check: Optional[Callable[[], Optional[str]]] = None,
    ) -> Dict[str, Any]:
        """Execute a scraping job end-to-end."""
        summary: Dict[str, Any] = {
            "pages_scraped": 0,
            "pages_failed": 0,
            "total_discovered": 0,
            "status": "completed",
        }
        start_url: str = ""

        try:
            async with async_session_factory() as session:
                job = await self._db_manager.get_job(session, job_id)

                if job is None:
                    logger.error("job_not_found", job_id=str(job_id))
                    summary["status"] = "failed"
                    return summary

                await self._db_manager.update_job_status(
                    session, job_id, JobStatus.RUNNING
                )
                await session.commit()

                crawl_mode = job.crawl_mode
                start_url = job.start_url
                url_rules = job.url_rules or []
                data_targets = job.data_targets or ["text"]
                credential_id = job.credential_id
                category_id = job.category_id
                raw_filter = job.filter_category_ids or []
                filter_category_ids: Set[str] = {str(cid) for cid in raw_filter}
                js_mode: str = getattr(job, "js_mode", "auto") or "auto"

            concurrency = self._app_config.concurrent_pages_per_job
            classify_in_thread = self._app_config.classification_run_in_subprocess
            worker_args = self._build_worker_args(data_targets)
            worker_args["js_mode"] = js_mode  # per-job override

            # Fetch stored cookies for this domain from Redis so thread
            # workers can inject them without needing Redis access.
            try:
                domain_cookies = await self._session_manager.get_cookies_for_domain(
                    start_url
                )
                worker_args["cookies"] = domain_cookies or {}
            except Exception:
                worker_args["cookies"] = {}

            logger.info(
                "job_config_loaded",
                job_id=str(job_id),
                crawl_mode=str(crawl_mode),
                js_mode=str(js_mode),
                start_url=start_url[:80],
                concurrency=concurrency,
                classify_in_subprocess=classify_in_thread,
                classification_enabled=self._classification_service.is_enabled,
            )
            await self._log(
                job_id, LogLevel.INFO,
                f"Starting {crawl_mode} scrape of {start_url}"
            )
            await self._log(
                job_id, LogLevel.INFO,
                f"Concurrency: up to {concurrency} parallel threads | "
                f"BART per-thread: {classify_in_thread}"
            )

            if crawl_mode == CrawlMode.SINGLE or str(crawl_mode) == "single":
                await self._log(job_id, LogLevel.INFO, "Mode: SINGLE")
                summary = await self._scrape_single(
                    job_id, start_url, worker_args, filter_category_ids
                )

            elif crawl_mode == CrawlMode.RULE_BASED or str(crawl_mode) == "rule_based":
                await self._log(
                    job_id, LogLevel.INFO,
                    f"Mode: RULE_BASED ({len(url_rules)} rules)"
                )

                def discover_rule(
                    html: str, base: str, seen: Set[str]
                ) -> List[str]:
                    return self._url_resolver.extract_links(
                        html, base, url_rules=url_rules, seen_urls=seen
                    )

                summary = await self._run_worker_pool(
                    job_id=job_id,
                    seed_urls=[start_url],
                    worker_args=worker_args,
                    filter_category_ids=filter_category_ids,
                    link_discovery_fn=discover_rule,
                    max_pages=self._app_config.max_pages_per_job,
                    max_depth=None,
                    concurrency=concurrency,
                    stop_check=stop_check,
                )

            elif crawl_mode == CrawlMode.INFINITE or str(crawl_mode) == "infinite":
                await self._log(job_id, LogLevel.INFO, "Mode: INFINITE")

                def discover_infinite(
                    html: str, base: str, seen: Set[str]
                ) -> List[str]:
                    return [
                        lnk for lnk in self._url_resolver.extract_links(
                            html, base, seen_urls=seen
                        )
                        if self._url_resolver.is_same_domain(lnk, start_url)
                    ]

                summary = await self._run_worker_pool(
                    job_id=job_id,
                    seed_urls=[start_url],
                    worker_args=worker_args,
                    filter_category_ids=filter_category_ids,
                    link_discovery_fn=discover_infinite,
                    max_pages=self._app_config.max_pages_per_job,
                    max_depth=self._app_config.max_crawl_depth,
                    concurrency=concurrency,
                    stop_check=stop_check,
                )

            elif crawl_mode == CrawlMode.CATEGORY or str(crawl_mode) == "category":
                await self._log(job_id, LogLevel.INFO, "Mode: CATEGORY")
                category_rules: List[Dict] = []

                if category_id is not None:
                    async with async_session_factory() as session:
                        cat = await self._db_manager.get_category(
                            session, category_id
                        )
                        if cat and cat.url_patterns:
                            category_rules = cat.url_patterns

                def discover_category(
                    html: str, base: str, seen: Set[str]
                ) -> List[str]:
                    return self._url_resolver.extract_links(
                        html, base,
                        url_rules=category_rules if category_rules else None,
                        seen_urls=seen,
                    )

                summary = await self._run_worker_pool(
                    job_id=job_id,
                    seed_urls=[start_url],
                    worker_args=worker_args,
                    filter_category_ids=filter_category_ids,
                    link_discovery_fn=discover_category,
                    max_pages=self._app_config.max_pages_per_job,
                    max_depth=None,
                    concurrency=concurrency,
                    stop_check=stop_check,
                )

            else:
                await self._log(
                    job_id, LogLevel.ERROR,
                    f"Unknown crawl mode: {crawl_mode}"
                )
                summary["status"] = "failed"

            # Determine final status
            if summary.get("status") == "stopped":
                final_status = JobStatus.STOPPED
            elif summary.get("status") == "paused":
                final_status = JobStatus.PAUSED
            elif (
                summary["pages_failed"] > 0 and summary["pages_scraped"] == 0
            ):
                final_status = JobStatus.FAILED
            else:
                final_status = JobStatus.COMPLETED

            # Write the final log entry FIRST so it is in the DB before
            # we flip status to COMPLETED. The WebSocket stops sending entries
            # the moment it sees status=completed, so "Job finished" and
            # "Classified as:" must already be committed before that flip.
            await self._log(
                job_id, LogLevel.INFO,
                f"Job finished: {summary['pages_scraped']} scraped, "
                f"{summary['pages_failed']} failed, "
                f"{summary['total_discovered']} discovered",
            )

            async with async_session_factory() as session:
                # Re-read current status before writing final status.
                # The API endpoint may have already set STOPPED or PAUSED
                # (via Redis signals + DB update) while the scraper was
                # running. If so, honour that — never override STOPPED/PAUSED
                # with COMPLETED. The scraper's summary only wins if the
                # job is still RUNNING in the DB.
                current_job = await self._db_manager.get_job(session, job_id)
                current_status = (
                    current_job.status if current_job else None
                )

                should_write_final = current_status == JobStatus.RUNNING

                if should_write_final:
                    await self._db_manager.update_job_status(
                        session, job_id, final_status
                    )
                else:
                    # Job was paused/stopped by the API — keep that status
                    logger.info(
                        "final_status_skipped",
                        job_id=str(job_id),
                        api_status=str(current_status),
                        scraper_status=str(final_status),
                    )

                await self._db_manager.update_job_progress(
                    session, job_id,
                    pages_scraped=summary["pages_scraped"],
                    pages_failed=summary["pages_failed"],
                    pages_discovered=summary["total_discovered"],
                )
                await session.commit()

        except Exception as exc:
            logger.error(
                "job_execution_error", job_id=str(job_id), error=str(exc)
            )
            summary["status"] = "failed"
            summary["error"] = str(exc)

            async with async_session_factory() as session:
                await self._db_manager.update_job_status(
                    session, job_id, JobStatus.FAILED, error=str(exc)
                )
                await session.commit()

            await self._log(job_id, LogLevel.ERROR, f"Job failed: {exc}")

        finally:
            if start_url:
                try:
                    await self._session_manager.persist_cookies(start_url)
                except Exception:
                    pass
            await self._session_manager.close_all()

        return summary


    #---------------------------------------------------------------------------
    # SINGLE-URL MODE
    async def _scrape_single(
        self,
        job_id: uuid.UUID,
        url: str,
        worker_args: Dict[str, Any],
        filter_category_ids: Set[str],
    ) -> Dict[str, Any]:
        """Scrape one URL in one thread."""
        loop = asyncio.get_event_loop()
        single_start_time = time.monotonic()

        with ThreadPoolExecutor(max_workers=1) as pool:
            args = {**worker_args, "url": url}
            page_result = await loop.run_in_executor(pool, _thread_worker, args)

        page_result["html"] = None  # free raw HTML — no longer needed
        await self._store_result(job_id, url, page_result, filter_category_ids)

        result_summary = {
            "pages_scraped": 1 if page_result["success"] else 0,
            "pages_failed": 0 if page_result["success"] else 1,
            "total_discovered": 1,
            "status": "completed",
        }

        await self._update_progress(
            job_id, result_summary, start_time=single_start_time
        )

        return result_summary


    #---------------------------------------------------------------------------
    # PARALLEL WORKER POOL — ONE URL PER THREAD
    async def _run_worker_pool(
        self,
        job_id: uuid.UUID,
        seed_urls: List[str],
        worker_args: Dict[str, Any],
        filter_category_ids: Set[str],
        link_discovery_fn: Callable[[str, str, Set[str]], List[str]],
        max_pages: int,
        max_depth: Optional[int],
        concurrency: int,
        stop_check: Optional[Callable],
    ) -> Dict[str, Any]:
        """
        Run the scraper in parallel using a ThreadPoolExecutor.
        """
        loop = asyncio.get_event_loop()
        seen_urls: Set[str] = set(seed_urls)
        url_queue: List[Tuple[str, int]] = [(url, 0) for url in seed_urls]
        summary: Dict[str, Any] = {
            "pages_scraped": 0,
            "pages_failed": 0,
            "total_discovered": len(seed_urls),
            "status": "completed",
        }
        start_time: float = time.monotonic()
        stopped: bool = False

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            in_flight: Dict[asyncio.Future, Tuple[str, int]] = {}

            while (url_queue or in_flight) and not stopped:

                # ── Stop / pause signal ───────────────────────────────
                if stop_check is not None:
                    signal = stop_check()
                    if signal == "stop":
                        summary["status"] = "stopped"
                        stopped = True
                        break
                    elif signal == "pause":
                        await asyncio.sleep(2)
                        continue

                # ── Fill slots: one thread per URL ────────────────────
                slots_free = concurrency - len(in_flight)

                while url_queue and slots_free > 0:
                    total_done = (
                        summary["pages_scraped"] + summary["pages_failed"]
                    )
                    if total_done >= max_pages:
                        stopped = True
                        break

                    url, depth = url_queue.pop(0)

                    if max_depth is not None and depth > max_depth:
                        continue

                    args = {**worker_args, "url": url}
                    future = loop.run_in_executor(pool, _thread_worker, args)
                    in_flight[future] = (url, depth)
                    slots_free -= 1

                    await self._log(
                        job_id, LogLevel.INFO,
                        f"Scraping: {url[:80]} "
                        f"(active: {len(in_flight)}, "
                        f"queued: {len(url_queue)})",
                        source_url=url,
                    )

                if not in_flight:
                    break

                # ── Await any thread to complete ──────────────────────
                done_set, _ = await asyncio.wait(
                    in_flight.keys(),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # ── Process each completed result ─────────────────────
                for future in done_set:
                    url, depth = in_flight.pop(future)

                    try:
                        page_result: Dict[str, Any] = await future
                    except Exception as exc:
                        logger.error(
                            "thread_error", url=url[:80], error=str(exc)
                        )
                        summary["pages_failed"] += 1
                        await self._log(
                            job_id, LogLevel.ERROR,
                            f"Thread error: {exc}",
                            source_url=url,
                        )
                        continue

                    await self._store_result(
                        job_id, url, page_result, filter_category_ids
                    )

                    if page_result["success"]:
                        summary["pages_scraped"] += 1
                        label_info = (
                            f" → {', '.join(page_result['labels'])}"
                            if page_result.get("labels")
                            else ""
                        )
                        await self._log(
                            job_id, LogLevel.INFO,
                            f"Scraped successfully{label_info}",
                            source_url=url,
                        )
                    else:
                        summary["pages_failed"] += 1
                        await self._log(
                            job_id, LogLevel.ERROR,
                            f"Failed: {page_result.get('error', '?')}",
                            source_url=url,
                        )

                    # Link discovery is done here, then immediately free the raw HTML
                    if page_result.get("html") and not stopped:
                        new_links = link_discovery_fn(
                            page_result["html"], url, seen_urls
                        )
                        page_result["html"] = None  # free immediately

                        for link in new_links:
                            if link not in seen_urls:
                                seen_urls.add(link)
                                url_queue.append((link, depth + 1))
                                summary["total_discovered"] += 1

                        if new_links:
                            await self._log(
                                job_id, LogLevel.INFO,
                                f"Discovered {len(new_links)} links "
                                f"(queue: {len(url_queue)})",
                                source_url=url,
                            )

                await self._update_progress(
                    job_id, summary, start_time=start_time
                )

            for future in in_flight:
                future.cancel()

        return summary

    #---------------------------------------------------------------------------
    # STORE RESULT
    async def _store_result(
        self,
        job_id: uuid.UUID,
        url: str,
        page_result: Dict[str, Any],
        filter_category_ids: Set[str],
    ) -> bool:
        """Classify (if not done in thread) and store to DB."""
        if not page_result["success"]:
            await self._store_error_result(
                job_id, url,
                page_result.get("http_status"),
                page_result.get("error") or "Unknown error",
            )
            return False

        content_blocks = page_result.get("content_blocks") or []
        page_title = page_result.get("page_title")
        http_status = page_result.get("http_status")
        labels: List[str] = list(page_result.get("labels") or [])

        # Classify in coordinator if thread didn't
        if not page_result.get("classified") and content_blocks:
            try:
                classification_result = (
                    await self._classification_service.classify(
                        title=page_title or "",
                        content_blocks=content_blocks,
                    )
                )
                labels = classification_result.labels
            except Exception as exc:
                logger.warning(
                    "coordinator_classification_failed",
                    url=url[:80],
                    error=str(exc),
                )

        async with async_session_factory() as db_session:
            assigned_categories = await self._resolve_categories(
                db_session=db_session,
                job_id=job_id,
                labels=labels,
            )

            if not self._should_save_result(
                assigned_categories, filter_category_ids
            ):
                await db_session.rollback()
                return False

            scrape_result = await self._db_manager.store_scrape_result(
                session=db_session,
                job_id=job_id,
                url=url,
                content=content_blocks,
                http_status=http_status,
                page_title=page_title,
            )

            if assigned_categories:
                await self._db_manager.assign_categories_to_result(
                    session=db_session,
                    scrape_result_id=scrape_result.id,
                    category_ids=[c.id for c in assigned_categories],
                )

            await db_session.commit()

        # Always log classification result so it appears in the job log stream.
        # Shows "Uncategorized" if BART found no labels above the threshold.
        category_names = [c.name for c in assigned_categories]
        await self._log(
            job_id, LogLevel.INFO,
            f"Classified as: {', '.join(category_names)}",
            source_url=url,
        )

        return True

    #---------------------------------------------------------------------------
    # CLASSIFICATION HELPERS
    async def _resolve_categories(
        self,
        db_session: Any,
        job_id: uuid.UUID,
        labels: List[str],
    ) -> List[Any]:
        if not labels:
            uncategorized = await self._db_manager.get_category_by_name(
                db_session, UNCATEGORIZED_NAME
            )
            if uncategorized is None:
                uncategorized = await self._db_manager.ensure_uncategorized_exists(
                    db_session
                )
            return [uncategorized]

        categories = []
        for label in labels:
            category, created = (
                await self._db_manager.get_or_create_category_by_name(
                    db_session, label
                )
            )
            categories.append(category)
            if created:
                await self._log(
                    job_id, LogLevel.INFO,
                    f"Auto-created category: {label}"
                )
        return categories

    def _should_save_result(
        self,
        assigned_categories: List[Any],
        filter_category_ids: Set[str],
    ) -> bool:
        if not filter_category_ids:
            return True
        for category in assigned_categories:
            if category.name == UNCATEGORIZED_NAME:
                return True
            if str(category.id) in filter_category_ids:
                return True
        return False


    #---------------------------------------------------------------------------
    # PERSISTENCE HELPERS
    async def _store_error_result(
        self,
        job_id: uuid.UUID,
        url: str,
        http_status: Optional[int],
        error: str,
    ) -> None:
        try:
            async with async_session_factory() as session:
                await self._db_manager.store_scrape_result(
                    session=session,
                    job_id=job_id,
                    url=url,
                    content=None,
                    http_status=http_status,
                    error=error,
                )
                await session.commit()
        except Exception as exc:
            logger.error(
                "store_error_result_failed", url=url[:80], error=str(exc)
            )

    async def _update_progress(
        self,
        job_id: uuid.UUID,
        summary: Dict[str, Any],
        start_time: Optional[float] = None,
    ) -> None:
        pages_per_second: Optional[float] = None

        if start_time is not None:
            elapsed = time.monotonic() - start_time
            total_done = summary["pages_scraped"] + summary["pages_failed"]
            if total_done > 0 and elapsed > 0.5:
                pages_per_second = round(
                    summary["pages_scraped"] / elapsed, 2
                )

        try:
            async with async_session_factory() as session:
                await self._db_manager.update_job_progress(
                    session=session,
                    job_id=job_id,
                    pages_scraped=summary["pages_scraped"],
                    pages_failed=summary["pages_failed"],
                    pages_discovered=summary["total_discovered"],
                    scrape_speed=pages_per_second,
                )
                await session.commit()
        except Exception as exc:
            logger.warning(
                "update_progress_failed", job_id=str(job_id), error=str(exc)
            )

    async def _log(
        self,
        job_id: uuid.UUID,
        level: LogLevel,
        message: str,
        source_url: Optional[str] = None,
    ) -> None:
        try:
            async with async_session_factory() as session:
                await self._db_manager.create_log_entry(
                    session=session,
                    job_id=job_id,
                    message=message,
                    level=level,
                    source_url=source_url,
                )
                await session.commit()
        except Exception as exc:
            logger.error(
                "log_write_failed", job_id=str(job_id), error=str(exc)
            )

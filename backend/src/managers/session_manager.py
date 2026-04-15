# =============================================================================
# Manages authenticated HTTP sessions for scraping.
# =============================================================================

from __future__ import annotations

import json
import uuid
from http.cookies import SimpleCookie
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import aiohttp
import redis.asyncio as aioredis

from backend.config import get_settings
from backend.logging_config import get_logger
from backend.src.services.encryption_service import EncryptionService
from backend.src.managers.database_manager import DatabaseManager
from backend.database.connection import async_session_factory

logger = get_logger("session_manager")

_COOKIE_KEY_PREFIX = "webscraper:session:cookies:"
_COOKIE_TTL_SECONDS = 86400


class SessionManager:

    def __init__(self) -> None:
        self._settings = get_settings()
        self._encryption = EncryptionService()
        self._db_manager = DatabaseManager()
        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=self._settings.redis_host,
                port=self._settings.redis_port,
                db=self._settings.redis_db,
                decode_responses=True,
            )
        return self._redis


    #---------------------------------------------------------------------------
    # PUBLIC API
    async def get_session(
        self,
        url: str,
        credential_id: Optional[uuid.UUID] = None,
    ) -> aiohttp.ClientSession:
        """Get or create an authenticated aiohttp session for the URL's domain."""
        domain = self._extract_domain(url)

        if domain in self._sessions and not self._sessions[domain].closed:
            return self._sessions[domain]

        headers = {
            "User-Agent": self._settings.scraper_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
        }

        cookie_jar = aiohttp.CookieJar(unsafe=True)
        restored = await self._restore_cookies(domain, cookie_jar)
        if restored:
            logger.info("cookies_restored", domain=domain)

        timeout = aiohttp.ClientTimeout(total=self._settings.scraper_default_timeout)
        connector = aiohttp.TCPConnector(
            limit=self._settings.scraper_max_concurrent_requests,
            limit_per_host=self._settings.scraper_max_concurrent_requests,
            enable_cleanup_closed=True,
            ttl_dns_cache=300,
        )
        session = aiohttp.ClientSession(
            headers=headers,
            cookie_jar=cookie_jar,
            timeout=timeout,
            connector=connector,
        )

        self._sessions[domain] = session

        if not restored:
            await self._try_auto_login(domain, session, credential_id)

        return session

    async def get_unauthenticated_session(self) -> aiohttp.ClientSession:
        """Get a generic unauthenticated session."""
        cache_key = "__unauthenticated__"

        if cache_key in self._sessions and not self._sessions[cache_key].closed:
            return self._sessions[cache_key]

        headers = {
            "User-Agent": self._settings.scraper_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        timeout = aiohttp.ClientTimeout(total=self._settings.scraper_default_timeout)
        connector = aiohttp.TCPConnector(
            limit=self._settings.scraper_max_concurrent_requests,
            enable_cleanup_closed=True,
        )
        session = aiohttp.ClientSession(
            headers=headers,
            timeout=timeout,
            connector=connector,
        )

        self._sessions[cache_key] = session
        return session

    async def get_cookies_for_domain(self, url: str) -> Dict[str, str]:
        """
        Get the cookies for a domain from Redis.
        """
        domain = self._extract_domain(url)
        try:
            redis_client = await self._get_redis()
            redis_key = f"{_COOKIE_KEY_PREFIX}{domain}"
            raw = await redis_client.get(redis_key)
            if raw is None:
                return {}
            cookies_data = json.loads(raw)
            return {
                c["key"]: c["value"]
                for c in cookies_data
                if "key" in c and "value" in c
            }
        except Exception as exc:
            logger.warning(
                "get_cookies_failed", domain=domain, error=str(exc)
            )
            return {}

    async def persist_cookies(self, url: str) -> None:
        """Save current cookies for a domain to Redis."""
        domain = self._extract_domain(url)

        if domain not in self._sessions:
            return

        session = self._sessions[domain]
        cookie_jar = session.cookie_jar

        cookies_data = []
        for cookie in cookie_jar:
            cookies_data.append({
                "key": cookie.key,
                "value": cookie.value,
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
                "secure": cookie.get("secure", ""),
            })

        if not cookies_data:
            return

        redis_client = await self._get_redis()
        redis_key = f"{_COOKIE_KEY_PREFIX}{domain}"
        await redis_client.setex(
            redis_key,
            _COOKIE_TTL_SECONDS,
            json.dumps(cookies_data),
        )
        logger.info("cookies_persisted", domain=domain, count=len(cookies_data))

    async def invalidate_session(self, url: str) -> None:
        """Close and remove a cached session, clearing Redis cookies."""
        domain = self._extract_domain(url)

        if domain in self._sessions:
            session = self._sessions.pop(domain)
            if not session.closed:
                await session.close()

        redis_client = await self._get_redis()
        redis_key = f"{_COOKIE_KEY_PREFIX}{domain}"
        await redis_client.delete(redis_key)

        logger.info("session_invalidated", domain=domain)

    async def close_all(self) -> None:
        """Close all cached sessions and the Redis connection."""
        for domain, session in self._sessions.items():
            if not session.closed:
                await session.close()
        self._sessions.clear()

        if self._redis is not None:
            await self._redis.close()
            self._redis = None

        logger.info("all_sessions_closed")


    #---------------------------------------------------------------------------
    # COOKIE PERSISTENCE
    async def _restore_cookies(
        self,
        domain: str,
        cookie_jar: aiohttp.CookieJar,
    ) -> bool:
        """Attempt to restore cookies from Redis into the given cookie jar."""
        try:
            redis_client = await self._get_redis()
            redis_key = f"{_COOKIE_KEY_PREFIX}{domain}"
            raw = await redis_client.get(redis_key)

            if raw is None:
                return False

            cookies_data = json.loads(raw)
            if not cookies_data:
                return False

            for cookie_dict in cookies_data:
                morsel_cookie = SimpleCookie()
                morsel_cookie[cookie_dict["key"]] = cookie_dict["value"]
                morsel = morsel_cookie[cookie_dict["key"]]
                morsel["domain"] = cookie_dict.get("domain", domain)
                morsel["path"] = cookie_dict.get("path", "/")
                cookie_jar.update_cookies(morsel_cookie)

            logger.info(
                "cookies_loaded_from_redis",
                domain=domain,
                count=len(cookies_data),
            )
            return True

        except Exception as exc:
            logger.warning("cookie_restore_failed", domain=domain, error=str(exc))
            return False


    #---------------------------------------------------------------------------
    # AUTO-LOGIN
    async def _try_auto_login(
        self,
        domain: str,
        session: aiohttp.ClientSession,
        credential_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """Attempt to auto-login using stored credentials for the domain."""
        credential = await self._fetch_credential(domain, credential_id)

        if credential is None:
            return False

        if not credential.get("login_url"):
            logger.info("no_login_url", domain=domain)
            return False

        try:
            password = self._encryption.decrypt(credential["encrypted_password"])
        except Exception as exc:
            logger.error("password_decryption_failed", domain=domain, error=str(exc))
            return False

        form_data = {
            credential.get("username_field", "username"): credential["username"],
            credential.get("password_field", "password"): password,
        }

        try:
            async with session.post(
                credential["login_url"],
                data=form_data,
                allow_redirects=True,
            ) as response:
                status = response.status

                if status >= 400:
                    logger.warning(
                        "auto_login_failed",
                        domain=domain,
                        status=status,
                    )
                    return False

                await self.persist_cookies(f"https://{domain}")
                logger.info("auto_login_success", domain=domain, status=status)
                return True

        except aiohttp.ClientError as exc:
            logger.error("auto_login_error", domain=domain, error=str(exc))
            return False

    async def _fetch_credential(
        self,
        domain: str,
        credential_id: Optional[uuid.UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch credential data from the database."""
        try:
            async with async_session_factory() as db_session:
                if credential_id is not None:
                    cred = await self._db_manager.get_credential(
                        db_session, credential_id
                    )
                else:
                    cred = await self._db_manager.get_credential_by_domain(
                        db_session, domain
                    )

                if cred is None:
                    return None

                return {
                    "username": cred.username,
                    "encrypted_password": cred.encrypted_password,
                    "login_url": cred.login_url,
                    "username_selector": cred.username_selector,
                    "password_selector": cred.password_selector,
                    "submit_selector": cred.submit_selector,
                    "username_field": _selector_to_field_name(
                        cred.username_selector, "username"
                    ),
                    "password_field": _selector_to_field_name(
                        cred.password_selector, "password"
                    ),
                }

        except Exception as exc:
            logger.error(
                "credential_fetch_failed", domain=domain, error=str(exc)
            )
            return None


    #---------------------------------------------------------------------------
    # UTILITIES
    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract the domain (netloc) from a URL."""
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        if ":" in domain:
            domain = domain.split(":")[0]
        return domain.lower()


def _selector_to_field_name(selector: Optional[str], default: str) -> str:
    """Extract a form field name from a CSS selector."""
    if not selector:
        return default

    if 'name="' in selector:
        start = selector.index('name="') + 6
        end = selector.index('"', start)
        return selector[start:end]

    if "name='" in selector:
        start = selector.index("name='") + 6
        end = selector.index("'", start)
        return selector[start:end]

    if "#" in selector:
        id_part = selector.split("#")[-1]
        for char in ("[", ":", " ", ".", ">"):
            if char in id_part:
                id_part = id_part.split(char)[0]
        if id_part:
            return id_part

    return default

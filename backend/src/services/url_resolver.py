#======================================================================================================
# URL resolution and filtering
#======================================================================================================

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from backend.config import get_app_config
from backend.logging_config import get_logger

logger = get_logger("url_resolver")


class URLResolver:
    """
    Extracts and filters URLs from HTML content.
    Supports configurable URL rules for controlling which links to follow.
    """

    def __init__(self) -> None:
        app_config = get_app_config()
        self._blocked_domains: List[str] = app_config.blocked_domains
        self._skip_extensions: List[str] = app_config.skip_extensions

    def extract_links(
        self,
        html: str,
        base_url: str,
        url_rules: Optional[List[Dict]] = None,
        seen_urls: Optional[Set[str]] = None,
    ) -> List[str]:
        """
        Extracts and filters URLs from HTML content.
        Supports configurable URL rules for controlling which links to follow.
        """
        if seen_urls is None:
            seen_urls = set()


        soup = BeautifulSoup(html, "html.parser")
        raw_links: List[str] = []

        # Collect href attributes from <a> tags
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if href:
                raw_links.append(href)

        logger.info(
            "links_discovered_raw",
            base_url=base_url[:80],
            raw_count=len(raw_links),
            seen_count=len(seen_urls),
        )

        local_seen: Set[str] = set(seen_urls)

        # Resolve, normalize, filter, and deduplicate
        resolved: List[str] = []
        for raw_href in raw_links:
            normalized = self.normalize_url(raw_href, base_url)

            if normalized is None:
                continue

            if normalized in local_seen:
                continue

            if not self._is_valid_url(normalized):
                continue

            if self._is_blocked(normalized):
                continue

            if self._has_skipped_extension(normalized):
                continue

            if url_rules and not self._matches_rules(normalized, url_rules):
                continue

            local_seen.add(normalized)
            resolved.append(normalized)

        logger.info(
            "links_after_filtering",
            base_url=base_url[:80],
            resolved_count=len(resolved),
            rules_count=len(url_rules) if url_rules else 0,
        )

        return resolved

    def normalize_url(self, href: str, base_url: str) -> Optional[str]:
        """
        Normalizes and validates a URL.
        """
        # Skip non-HTTP schemes and special links
        if href.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
            return None

        # Resolve relative URLs
        absolute = urljoin(base_url, href)

        # Parse and validate
        parsed = urlparse(absolute)

        if parsed.scheme not in ("http", "https"):
            return None

        if not parsed.netloc:
            return None

        # Rebuild without fragment, normalize path
        clean_path = parsed.path.rstrip("/") or "/"
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc.lower(),
            clean_path,
            parsed.params,
            parsed.query,
            "",  # strip fragment
        ))

        return normalized

    def matches_rules(
        self,
        url: str,
        url_rules: List[Dict],
    ) -> bool:
        """
        Public wrapper for rule matching.
        Returns True if the URL matches at least one rule.
        """
        return self._matches_rules(url, url_rules)

    def get_domain(self, url: str) -> str:
        """Extract the domain from a URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if ":" in domain:
            domain = domain.split(":")[0]
        return domain

    def is_same_domain(self, url1: str, url2: str) -> bool:
        """Check if two URLs belong to the same domain."""
        return self.get_domain(url1) == self.get_domain(url2)


    #---------------------------------------------------------------------------
    # INTERNAL FILTERS
    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Basic URL validity check."""
        parsed = urlparse(url)
        return bool(parsed.scheme) and bool(parsed.netloc)

    def _is_blocked(self, url: str) -> bool:
        """Check if the URL's domain is in the blocked list."""
        domain = self.get_domain(url)
        for blocked in self._blocked_domains:
            if domain == blocked or domain.endswith(f".{blocked}"):
                return True
        return False

    def _has_skipped_extension(self, url: str) -> bool:
        """Check if the URL points to a file type we should skip."""
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        for ext in self._skip_extensions:
            if path_lower.endswith(ext):
                return True
        return False

    @staticmethod
    def _matches_rules(url: str, url_rules: List[Dict]) -> bool:
        """
        Check if a URL matches at least one of the given rules.
        Rule types:
            - "contains": URL contains the pattern string
            - "starts_with": URL starts with the pattern string
            - "ends_with": URL ends with the pattern string
            - "regex": URL matches the regex pattern
            - "domain": URL's domain matches the pattern
        """
        url_lower = url.lower()

        for rule in url_rules:
            rule_type = rule.get("type", "").lower()
            pattern = rule.get("pattern", "").lower()

            if not rule_type or not pattern:
                continue

            if rule_type == "contains":
                if pattern in url_lower:
                    return True

            elif rule_type == "starts_with":
                if url_lower.startswith(pattern):
                    return True

            elif rule_type == "ends_with":
                if url_lower.endswith(pattern):
                    return True

            elif rule_type == "regex":
                try:
                    if re.search(pattern, url_lower):
                        return True
                except re.error:
                    logger.warning("invalid_regex_rule", pattern=pattern)

            elif rule_type == "domain":
                parsed = urlparse(url_lower)
                domain = parsed.netloc
                if ":" in domain:
                    domain = domain.split(":")[0]
                if domain == pattern or domain.endswith(f".{pattern}"):
                    return True

        return False

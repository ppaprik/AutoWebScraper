#======================================================================================================
# Detects whether a page is behind a wall.
#======================================================================================================

from __future__ import annotations

import enum
import re
from typing import Dict, List, Optional


class WallType(str, enum.Enum):
    """Classification of the detected wall type."""
    NONE = "none"
    CLOUDFLARE = "cloudflare"
    RECAPTCHA = "recaptcha"
    HCAPTCHA = "hcaptcha"
    DATADOME = "datadome"
    PERIMETERX = "perimeterx"
    LOGIN_WALL = "login_wall"
    COOKIE_CONSENT = "cookie_consent"
    PAYWALL = "paywall"
    RATE_LIMIT = "rate_limit"
    SESSION_EXPIRED = "session_expired"
    IP_BAN = "ip_ban"


class WallAction(str, enum.Enum):
    """Recommended action when a wall is detected."""
    NONE = "none"        # No wall
    SKIP = "skip"        # Cannot bypass
    LOGIN = "login"      # Try auto-login with stored credentials, then retry
    DISMISS = "dismiss"  # Auto-dismiss (cookie consent) via Playwright
    RETRY = "retry"      # Back off and retry (rate limit)


class WallDetectionResult:
    """Result of a wall detection analysis."""

    def __init__(
        self,
        wall_type: WallType,
        action: WallAction,
        confidence: str,
        signals: List[str],
        retry_after_seconds: Optional[float] = None,
    ) -> None:
        self.wall_type = wall_type
        self.action = action
        self.confidence = confidence      # "high" | "medium" | "low"
        self.signals = signals            # Human-readable list of matched signals
        self.retry_after_seconds = retry_after_seconds
        self.is_blocked = action != WallAction.NONE

    def __repr__(self) -> str:
        return (
            f"<WallDetectionResult type={self.wall_type.value} "
            f"action={self.action.value} signals={self.signals}>"
        )


#----------------------------------------------------------------------------------------------------
# Body pattern constants
_CF_BODY_PATTERNS: List[str] = [
    "checking your browser",
    "please wait while we check your browser",
    "ddos-guard",
    "cloudflare ray id",
    "cf-browser-verification",
    "enable javascript and cookies to continue",
    "attention required! | cloudflare",
]

_RECAPTCHA_PATTERNS: List[str] = [
    "grecaptcha",
    "recaptcha/api.js",
    "data-sitekey",
    "g-recaptcha",
    "recaptcha.net/recaptcha",
]

_HCAPTCHA_PATTERNS: List[str] = [
    "hcaptcha.com/1/api.js",
    "data-hcaptcha-sitekey",
    "hcaptcha-challenge",
]

_DATADOME_PATTERNS: List[str] = [
    "datadome",
    "dd_referrer",
    "device-is-challenged",
]

_PERIMETERX_PATTERNS: List[str] = [
    "perimeterx",
    "_pxhd",
    "px-captcha",
    "human.px-cdn.net",
    "PerimeterX",
]

_LOGIN_PATTERNS: List[str] = [
    'type="password"',
    "login-form",
    "signin-form",
    "sign-in-form",
    'action="/login"',
    'action="/signin"',
    'action="/sign-in"',
    "you must be logged in",
    "please log in to continue",
    "please sign in to continue",
    "members only",
]

_PAYWALL_PATTERNS: List[str] = [
    "subscribe to read",
    "subscribe to continue",
    "subscription required",
    "become a member to read",
    "this article is for subscribers",
    "piano.io",
    "tinypass.com",
    "unlock this article",
    "premium content",
]

_COOKIE_CONSENT_PATTERNS: List[str] = [
    "cookieconsent",
    "cookie-consent",
    "cookie_consent",
    "gdpr-consent",
    "CookieBot",
    "OneTrust",
    "onetrust-accept-btn",
    "cc-allow",
    "js-cookie-consent",
    "accept all cookies",
    "accept cookies",
]

_SESSION_EXPIRED_PATTERNS: List[str] = [
    "session expired",
    "session has expired",
    "your session has timed out",
    "session timeout",
    "please login again",
    "token expired",
    "authentication expired",
]

# URL path patterns that indicate a login wall redirect
_LOGIN_URL_PATTERNS: List[re.Pattern] = [
    re.compile(r"/login", re.IGNORECASE),
    re.compile(r"/signin", re.IGNORECASE),
    re.compile(r"/sign-in", re.IGNORECASE),
    re.compile(r"/auth/", re.IGNORECASE),
    re.compile(r"/account/login", re.IGNORECASE),
    re.compile(r"[?&]redirect", re.IGNORECASE),
    re.compile(r"[?&]next=", re.IGNORECASE),
    re.compile(r"[?&]return=", re.IGNORECASE),
]


class WallDetector:
    """
    Analyses an HTTP response (status, headers, cookies, body) and determines
    whether a bot-protection, auth, or access wall is present.

    Designed to run synchronously inside a thread — no I/O, no async.
    """

    def detect(
        self,
        status: int,
        headers: Dict[str, str],
        html: str,
        final_url: Optional[str] = None,
        cookie_names: Optional[List[str]] = None,
    ) -> WallDetectionResult:
        """
        Detects whether a bot-protection, auth, or access wall is present.
        """
        h = {k.lower(): v.lower() for k, v in headers.items()}
        body = html.lower()
        cookies = [c.lower() for c in (cookie_names or [])]
        signals: List[str] = []

        # Cloudflare
        has_cf_ray = "cf-ray" in h
        has_cf_cookie = any(c in cookies for c in ("__cf_bm", "cf_clearance"))
        cf_body = any(p in body for p in _CF_BODY_PATTERNS)

        if has_cf_ray and status in (403, 429, 503):
            signals.append(f"cf-ray header + HTTP {status}")
            if cf_body:
                signals.append("cloudflare challenge body text")
            return WallDetectionResult(
                WallType.CLOUDFLARE, WallAction.SKIP, "high", signals
            )

        if has_cf_cookie and cf_body:
            signals.append("__cf_bm cookie + challenge body")
            return WallDetectionResult(
                WallType.CLOUDFLARE, WallAction.SKIP, "high", signals
            )

        if cf_body and status in (403, 503):
            signals.append("cloudflare challenge body only")
            return WallDetectionResult(
                WallType.CLOUDFLARE, WallAction.SKIP, "medium", signals
            )

        # reCAPTCHA
        if any(p in body for p in _RECAPTCHA_PATTERNS):
            signals.append("recaptcha scripts/attributes in body")
            return WallDetectionResult(
                WallType.RECAPTCHA, WallAction.SKIP, "high", signals
            )

        # hCaptcha
        if any(p in body for p in _HCAPTCHA_PATTERNS):
            signals.append("hcaptcha scripts/attributes in body")
            return WallDetectionResult(
                WallType.HCAPTCHA, WallAction.SKIP, "high", signals
            )

        # DataDome
        has_dd_header = "x-datadome" in h or "x-dd-b" in h
        has_dd_cookie = any(c in cookies for c in ("datadome", "_dd_s"))
        dd_body = any(p in body for p in _DATADOME_PATTERNS)

        if has_dd_header or (has_dd_cookie and status in (403, 401)):
            signals.append(f"datadome header/cookie + HTTP {status}")
            return WallDetectionResult(
                WallType.DATADOME, WallAction.SKIP, "high", signals
            )

        if dd_body and status in (403, 401):
            signals.append("datadome body pattern + blocked status")
            return WallDetectionResult(
                WallType.DATADOME, WallAction.SKIP, "medium", signals
            )

        # PerimeterX
        has_px_cookie = any(
            c in cookies for c in ("_px3", "_pxhd", "_pxvid")
        )
        px_body = any(p.lower() in body for p in _PERIMETERX_PATTERNS)

        if has_px_cookie and status in (403, 401):
            signals.append(f"perimeterx cookie + HTTP {status}")
            return WallDetectionResult(
                WallType.PERIMETERX, WallAction.SKIP, "high", signals
            )

        if px_body and status in (403, 401):
            signals.append("perimeterx body pattern + blocked status")
            return WallDetectionResult(
                WallType.PERIMETERX, WallAction.SKIP, "medium", signals
            )

        # Rate limit
        if status == 429:
            retry_after: Optional[float] = None
            if "retry-after" in h:
                try:
                    retry_after = float(h["retry-after"])
                except ValueError:
                    retry_after = 60.0
            signals.append(f"HTTP 429 Too Many Requests (retry-after: {retry_after}s)")
            return WallDetectionResult(
                WallType.RATE_LIMIT, WallAction.RETRY, "high", signals,
                retry_after_seconds=retry_after or 60.0,
            )

        # IP ban
        # 403 with no bot-detection headers = likely IP-level block
        if status == 403 and not has_cf_ray and not has_dd_header:
            signals.append("HTTP 403 with no known bot-detection headers")
            return WallDetectionResult(
                WallType.IP_BAN, WallAction.SKIP, "low", signals
            )

        # Session expired
        if any(p in body for p in _SESSION_EXPIRED_PATTERNS):
            signals.append("session-expired text in body")
            return WallDetectionResult(
                WallType.SESSION_EXPIRED, WallAction.LOGIN, "high", signals
            )

        # Login wall (redirect-based)
        if final_url and any(p.search(final_url) for p in _LOGIN_URL_PATTERNS):
            signals.append(f"redirected to login URL: {final_url}")
            return WallDetectionResult(
                WallType.LOGIN_WALL, WallAction.LOGIN, "high", signals
            )

        # Login wall (form-based)
        if any(p in body for p in _LOGIN_PATTERNS):
            signals.append("login form detected in body")
            return WallDetectionResult(
                WallType.LOGIN_WALL, WallAction.LOGIN, "medium", signals
            )

        # Paywall
        if any(p in body for p in _PAYWALL_PATTERNS):
            signals.append("paywall text detected in body")
            return WallDetectionResult(
                WallType.PAYWALL, WallAction.SKIP, "medium", signals
            )

        # Cookie consent
        # Lower priority than all others — only checked if nothing above fired
        if any(p.lower() in body for p in _COOKIE_CONSENT_PATTERNS):
            signals.append("cookie consent widget detected")
            return WallDetectionResult(
                WallType.COOKIE_CONSENT, WallAction.DISMISS, "medium", signals
            )

        # No wall
        return WallDetectionResult(
            WallType.NONE, WallAction.NONE, "high", []
        )

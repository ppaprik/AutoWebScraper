#======================================================================================================
# Detects whether a page is rendered by JavaScript.
#======================================================================================================

from __future__ import annotations

import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup


class JSDetectionResult:
    """Outcome of a JS detection analysis pass."""

    def __init__(
        self,
        score: int,
        threshold: int,
        signals_fired: List[str],
    ) -> None:
        self.score = score
        self.threshold = threshold
        self.signals_fired = signals_fired
        self.needs_js: bool = score >= threshold

    def __repr__(self) -> str:
        return (
            f"<JSDetectionResult score={self.score}/{self.threshold} "
            f"needs_js={self.needs_js} signals={self.signals_fired}>"
        )


class JSDetector:
    _NOSCRIPT_MIN_CHARS: int = 30
    _MIN_BODY_TEXT_CHARS: int = 150

    _SPA_GLOBALS: List[str] = [
        "window.__INITIAL_STATE__",
        "window.__NEXT_DATA__",
        "window.__NUXT__",
        "window.__REDUX_STATE__",
        "__svelte",
        "window.__APP_STATE__",
    ]

    _REACT_SIGNALS: List[str] = [
        "data-reactroot",
        "_next/static/",
        "react.production.min.js",
    ]

    _VUE_SIGNALS: List[str] = [
        "vue.min.js",
        "vue.runtime.min.js",
        "__vue_store__",
    ]

    _ANGULAR_SIGNALS: List[str] = [
        "ng-version",
        "angular.min.js",
    ]

    def __init__(self, threshold: int = 4) -> None:
        self._threshold = threshold

    def detect(
        self,
        html: str,
        content_blocks: Optional[List[Dict]] = None,
        response_headers: Optional[Dict[str, str]] = None,
    ) -> JSDetectionResult:
        """
        Detects whether a page is rendered by JavaScript.
        """
        score = 0
        signals: List[str] = []
        headers = {k.lower(): v for k, v in (response_headers or {}).items()}
        soup = BeautifulSoup(html, "lxml")

        # Signal: zero content blocks
        if content_blocks is not None and len(content_blocks) == 0:
            score += 4
            signals.append("no_content_extracted(+4)")

        # Signal: empty SPA root element
        for root_id in ("root", "app", "__next", "app-root", "vue-app"):
            el = soup.find(id=root_id)
            if el is not None:
                if len(el.get_text(strip=True)) < 20:
                    score += 3
                    signals.append(f"empty_root_#{root_id}(+3)")
                    break

        # Signal: noscript with substantial text
        for noscript in soup.find_all("noscript"):
            if len(noscript.get_text(strip=True)) >= self._NOSCRIPT_MIN_CHARS:
                score += 3
                signals.append("noscript_content(+3)")
                break

        # Signal: SPA bootstrap globals
        for global_name in self._SPA_GLOBALS:
            if global_name in html:
                score += 2
                signals.append(f"spa_global:{global_name}(+2)")
                break

        # Signal: React
        for sig in self._REACT_SIGNALS:
            if sig in html:
                score += 2
                signals.append(f"react:{sig}(+2)")
                break

        # Signal: Vue
        for sig in self._VUE_SIGNALS:
            if sig in html:
                score += 2
                signals.append(f"vue:{sig}(+2)")
                break

        if soup.find(attrs=re.compile(r"^data-v-")):
            score += 2
            signals.append("vue:data-v-attr(+2)")

        # Signal: Angular
        for sig in self._ANGULAR_SIGNALS:
            if sig in html:
                score += 2
                signals.append(f"angular:{sig}(+2)")
                break

        # Signal: very thin body text
        body = soup.find("body")
        if body is not None:
            body_text = body.get_text(separator=" ", strip=True)
            if len(body_text) < self._MIN_BODY_TEXT_CHARS:
                score += 2
                signals.append(f"thin_body:{len(body_text)}chars(+2)")

        # Signal: x-powered-by header
        powered_by = headers.get("x-powered-by", "").lower()
        if any(fw in powered_by for fw in ("next.js", "nuxt", "angular")):
            score += 1
            signals.append(f"x-powered-by:{powered_by}(+1)")

        return JSDetectionResult(
            score=score,
            threshold=self._threshold,
            signals_fired=signals,
        )

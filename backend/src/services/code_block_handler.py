#======================================================================================================
# Detects and preserves code blocks in HTML content.
#======================================================================================================

from __future__ import annotations

import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag

from backend.config import get_app_config
from backend.logging_config import get_logger


logger = get_logger("code_block_handler")

# CSS class names that indicate code/monospace content
_CODE_CLASS_PATTERNS = [
    "highlight",
    "code",
    "syntax",
    "prism",
    "hljs",
    "codehilite",
    "sourceCode",
    "listing",
    "mono",
    "monospace",
    "console",
    "terminal",
    "shell",
    "bash",
    "language-",
    "lang-",
]

# HTML tags that explicitly mark code content
_CODE_TAGS = {"pre", "code", "samp", "kbd"}


class CodeBlockHandler:
    """
    Detects and preserves code blocks in HTML content.
    """

    def __init__(self) -> None:
        app_config = get_app_config()
        self._min_symbol_density: float = app_config.min_symbol_density
        self._code_symbols: List[str] = app_config.code_symbols

    def extract_code_blocks(self, soup: BeautifulSoup) -> List[Dict]:
        code_blocks: List[Dict] = []
        seen_elements: set = set()

        #Pass 1 -> Explicit code tags
        for tag_name in ("pre", "code", "samp", "kbd"):
            for element in soup.find_all(tag_name):
                element_id = id(element)

                # Skip if this element is nested inside one we already processed
                if element_id in seen_elements:
                    continue

                # Skip nested <code> inside <pre> — we'll get it from the <pre>
                if tag_name == "code" and element.parent and element.parent.name == "pre":
                    continue

                # Mark this element and all children as seen
                self._mark_seen(element, seen_elements)

                raw_text = self._extract_text_preserving_format(element)
                if not raw_text.strip():
                    continue

                language = self._detect_language(element, raw_text)

                code_blocks.append({
                    "type": "code_block",
                    "language": language,
                    "content": raw_text,
                })

        # Pass 2 -> Structural detection (no explicit code tags)
        for element in soup.find_all(["div", "span", "p", "td"]):
            element_id = id(element)

            if element_id in seen_elements:
                continue

            # Check CSS class hints
            if self._has_code_class(element):
                self._mark_seen(element, seen_elements)
                raw_text = self._extract_text_preserving_format(element)
                if raw_text.strip():
                    language = self._detect_language(element, raw_text)
                    code_blocks.append({
                        "type": "code_block",
                        "language": language,
                        "content": raw_text,
                    })
                continue

            # Check symbol density for untagged code
            raw_text = self._extract_text_preserving_format(element)
            if not raw_text.strip():
                continue

            if len(raw_text.strip()) < 20:
                continue

            if self._is_code_by_density(raw_text):
                self._mark_seen(element, seen_elements)
                language = self._detect_language(element, raw_text)
                code_blocks.append({
                    "type": "code_block",
                    "language": language,
                    "content": raw_text,
                })

        return code_blocks

    def is_code_element(self, element: Tag) -> bool:
        """
        Check if an element is likely to contain code.
        """
        if element.name in _CODE_TAGS:
            return True

        if self._has_code_class(element):
            return True

        text = self._extract_text_preserving_format(element)
        if len(text.strip()) >= 20 and self._is_code_by_density(text):
            return True

        return False

    def get_code_elements_set(self, soup: BeautifulSoup) -> set:
        """
        Find all code elements in the parsed HTML.
        Returns a set of element IDs.
        """
        code_ids: set = set()

        for tag_name in _CODE_TAGS:
            for element in soup.find_all(tag_name):
                self._mark_seen(element, code_ids)

        for element in soup.find_all(["div", "span", "p", "td"]):
            if id(element) in code_ids:
                continue
            if self._has_code_class(element):
                self._mark_seen(element, code_ids)
                continue
            text = self._extract_text_preserving_format(element)
            if len(text.strip()) >= 20 and self._is_code_by_density(text):
                self._mark_seen(element, code_ids)

        return code_ids


    #---------------------------------------------------------------------------
    # LANGUAGE DETECTION
    def _detect_language(self, element: Tag, text: str) -> str:
        """
        Attempt to detect the programming language from CSS classes,
        data attributes, or content heuristics.
        """
        # Check CSS classes for language hints
        classes = self._get_classes(element)
        for cls in classes:
            cls_lower = cls.lower()

            # Common patterns: language-python, lang-js, highlight-ruby
            for prefix in ("language-", "lang-", "highlight-"):
                if cls_lower.startswith(prefix):
                    lang = cls_lower[len(prefix):]
                    if lang:
                        return self._normalize_language(lang)

            # Direct language name as class
            normalized = self._normalize_language(cls_lower)
            if normalized != "unknown":
                return normalized

        # Check parent element classes too
        if element.parent and isinstance(element.parent, Tag):
            parent_classes = self._get_classes(element.parent)
            for cls in parent_classes:
                cls_lower = cls.lower()
                for prefix in ("language-", "lang-", "highlight-"):
                    if cls_lower.startswith(prefix):
                        lang = cls_lower[len(prefix):]
                        if lang:
                            return self._normalize_language(lang)

        # Check data-language attribute
        data_lang = element.get("data-language") or element.get("data-lang")
        if data_lang:
            return self._normalize_language(str(data_lang).lower())

        # Content-based heuristics
        return self._guess_language_from_content(text)

    @staticmethod
    def _normalize_language(raw: str) -> str:
        """Map common language aliases to canonical names."""
        language_map = {
            "py": "python",
            "python": "python",
            "python3": "python",
            "js": "javascript",
            "javascript": "javascript",
            "jsx": "javascript",
            "ts": "typescript",
            "typescript": "typescript",
            "tsx": "typescript",
            "rb": "ruby",
            "ruby": "ruby",
            "sh": "bash",
            "bash": "bash",
            "shell": "bash",
            "zsh": "bash",
            "css": "css",
            "html": "html",
            "xml": "xml",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "sql": "sql",
            "java": "java",
            "c": "c",
            "cpp": "cpp",
            "c++": "cpp",
            "csharp": "csharp",
            "cs": "csharp",
            "go": "go",
            "golang": "go",
            "rust": "rust",
            "rs": "rust",
            "php": "php",
            "swift": "swift",
            "kotlin": "kotlin",
            "kt": "kotlin",
            "scala": "scala",
            "r": "r",
            "dart": "dart",
            "lua": "lua",
            "perl": "perl",
            "powershell": "powershell",
            "ps1": "powershell",
            "dockerfile": "dockerfile",
            "docker": "dockerfile",
            "makefile": "makefile",
            "make": "makefile",
            "toml": "toml",
            "ini": "ini",
            "conf": "ini",
            "md": "markdown",
            "markdown": "markdown",
            "plaintext": "plaintext",
            "text": "plaintext",
            "txt": "plaintext",
        }
        return language_map.get(raw.strip(), "unknown")

    @staticmethod
    def _guess_language_from_content(text: str) -> str:
        """Use simple heuristics to guess language from code content."""
        lines = text.strip().split("\n")
        first_lines = "\n".join(lines[:10]).lower()

        # Python indicators
        if re.search(r"^(def |class |import |from .+ import |if __name__)", first_lines, re.MULTILINE):
            return "python"

        # JavaScript/TypeScript indicators
        if re.search(r"(const |let |var |function |=>|require\(|import .+ from)", first_lines):
            return "javascript"

        # HTML indicators
        if re.search(r"<(!DOCTYPE|html|head|body|div|span|p )", first_lines, re.IGNORECASE):
            return "html"

        # CSS indicators
        if re.search(r"[{}\s]*(margin|padding|display|font-size|color)\s*:", first_lines):
            return "css"

        # SQL indicators
        if re.search(r"^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\s", first_lines, re.IGNORECASE | re.MULTILINE):
            return "sql"

        # Shell/bash indicators
        if re.search(r"^(#!/bin/|apt-get|sudo |echo |export |cd |ls |mkdir )", first_lines, re.MULTILINE):
            return "bash"

        # JSON indicators
        stripped = text.strip()
        if (stripped.startswith("{") and stripped.endswith("}")) or \
           (stripped.startswith("[") and stripped.endswith("]")):
            return "json"

        return "unknown"


    #---------------------------------------------------------------------------
    # SYMBOL DENSITY ANALYSIS
    def _is_code_by_density(self, text: str) -> bool:
        """
        Determine if text is likely code based on symbol density.
        Counts code-characteristic symbols and compares to total length.
        """
        if not text.strip():
            return False

        total_chars = len(text)
        if total_chars == 0:
            return False

        symbol_count = 0
        for char in text:
            if char in self._code_symbols_set:
                symbol_count += 1

        density = symbol_count / total_chars

        # Also check for consistent indentation (2+ spaces or tabs at line starts)
        lines = text.split("\n")
        indented_lines = 0
        total_lines = 0
        for line in lines:
            if line.strip():
                total_lines += 1
                if line.startswith("  ") or line.startswith("\t"):
                    indented_lines += 1

        indentation_ratio = indented_lines / max(total_lines, 1)

        # Code if high symbol density OR moderate density + high indentation
        if density >= self._min_symbol_density:
            return True

        if density >= (self._min_symbol_density * 0.6) and indentation_ratio >= 0.4:
            return True

        return False

    @property
    def _code_symbols_set(self) -> set:
        """Cached set of code symbols for O(1) lookup."""
        if not hasattr(self, "_cached_symbols_set"):
            self._cached_symbols_set = set("".join(self._code_symbols))
        return self._cached_symbols_set


    #---------------------------------------------------------------------------
    # TEXT EXTRACTION HELPERS
    @staticmethod
    def _extract_text_preserving_format(element: Tag) -> str:
        """
        Extract text from an element while preserving whitespace,
        indentation, and line breaks exactly as they appear.
        """
        # For <pre> tags, get_text() preserves whitespace by default
        if element.name == "pre":
            return element.get_text()

        # For other elements, we need to be more careful
        parts: List[str] = []
        for child in element.descendants:
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif isinstance(child, Tag) and child.name == "br":
                parts.append("\n")

        return "".join(parts)

    @staticmethod
    def _has_code_class(element: Tag) -> bool:
        """Check if an element has CSS classes that indicate code content."""
        classes = element.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()

        for cls in classes:
            cls_lower = cls.lower()
            for pattern in _CODE_CLASS_PATTERNS:
                if pattern in cls_lower:
                    return True

        # Also check inline style for monospace font
        style = element.get("style", "")
        if isinstance(style, str):
            style_lower = style.lower()
            if "monospace" in style_lower or "courier" in style_lower:
                return True

        return False

    @staticmethod
    def _get_classes(element: Tag) -> List[str]:
        """Safely get the list of CSS classes from an element."""
        classes = element.get("class", [])
        if isinstance(classes, str):
            return classes.split()
        return list(classes)

    @staticmethod
    def _mark_seen(element: Tag, seen: set) -> None:
        """Mark an element and all its descendants as seen."""
        seen.add(id(element))
        for descendant in element.descendants:
            if isinstance(descendant, Tag):
                seen.add(id(descendant))

#======================================================================================================
# Extracts clean, structured text content from raw HTML
#======================================================================================================

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from readability import Document as ReadabilityDocument

from backend.config import get_app_config
from backend.logging_config import get_logger
from backend.src.services.code_block_handler import CodeBlockHandler


logger = get_logger("content_extractor")


class ContentExtractor:
    """
    Extracts clean, structured text content from raw HTML
    """

    def __init__(self) -> None:
        app_config = get_app_config()
        self._strip_tags: List[str] = app_config.strip_tags
        self._strip_classes: List[str] = app_config.strip_classes
        self._min_text_density: float = app_config.min_text_density
        self._min_block_words: int = app_config.min_block_words
        self._code_handler = CodeBlockHandler()

    def extract(
        self,
        html: str,
        url: str = "",
        data_targets: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extracts clean, structured text content from raw HTML.
        Preserves code blocks, headings, and paragraph structure.
        Strips navigation, ads, scripts, and other non-content elements.
        """
        if not html or not html.strip():
            return []

        if data_targets is None or not data_targets:
            data_targets = ["text"]

        blocks: List[Dict[str, Any]] = []

        # Stage 1: Readability — isolate main content
        main_html = self._readability_extract(html, url)

        # Stage 2: Parse and apply DOM filtering
        soup = BeautifulSoup(main_html, "lxml")
        self._remove_unwanted_elements(soup)

        # Stage 3: Extract code blocks FIRST (they are never noise)
        code_blocks = self._code_handler.extract_code_blocks(soup)
        code_element_ids = self._code_handler.get_code_elements_set(soup)

        # Stage 4: Extract text content with density scoring
        text_blocks = self._extract_text_blocks(soup, code_element_ids)

        # Stage 5: Post-processing — merge fragments, clean up
        text_blocks = self._post_process(text_blocks)

        # Stage 6: Interleave code blocks with text blocks
        blocks = self._interleave_blocks(text_blocks, code_blocks, soup)

        # Stage 7: Handle optional data targets
        if "headers" in data_targets:
            header_blocks = self._extract_headers(html)
            blocks = header_blocks + blocks

        if "footers" in data_targets:
            footer_blocks = self._extract_footers(html)
            blocks = blocks + footer_blocks

        if "ads" in data_targets:
            ad_blocks = self._extract_ads(html)
            blocks = blocks + ad_blocks

        # Filter out empty blocks
        blocks = [b for b in blocks if b.get("content", "").strip()]

        logger.info(
            "extraction_complete",
            url=url[:80],
            block_count=len(blocks),
            code_blocks=len(code_blocks),
        )

        return blocks

    def extract_title(self, html: str) -> Optional[str]:
        """Extract the page title from <title> tag."""
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)
        return None


    #---------------------------------------------------------------------------
    # STAGE 1: READABILITY
    @staticmethod
    def _readability_extract(html: str, url: str = "") -> str:
        """
        Use the readability algorithm to isolate the main content area.
        Falls back to the original HTML if readability fails.
        """
        try:
            doc = ReadabilityDocument(html, url=url)
            content_html = doc.summary()
            if content_html and len(content_html.strip()) > 100:
                return content_html
        except Exception as exc:
            logger.warning("readability_failed", url=url[:80], error=str(exc))

        return html


    #---------------------------------------------------------------------------
    # STAGE 2: DOM FILTERING
    def _remove_unwanted_elements(self, soup: BeautifulSoup) -> None:
        """
        Remove non-content elements from the DOM.
        This modifies the soup in place.
        """
        # Remove HTML comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove tags by name (nav, script, style, etc.)
        for tag_name in self._strip_tags:
            for element in soup.find_all(tag_name):
                # But NEVER remove code — check first
                if not self._code_handler.is_code_element(element):
                    element.decompose()

        # Remove elements by CSS class or ID
        for element in soup.find_all(True):
            if self._has_strip_class(element):
                # Check it's not a code element before removing
                if not self._code_handler.is_code_element(element):
                    element.decompose()

        # Remove hidden elements
        for element in soup.find_all(True, style=True):
            style = element.get("style", "").lower()
            if "display:none" in style.replace(" ", "") or \
               "visibility:hidden" in style.replace(" ", ""):
                if not self._code_handler.is_code_element(element):
                    element.decompose()

    def _has_strip_class(self, element: Tag) -> bool:
        """Check if an element has a CSS class or ID that indicates non-content."""
        classes = element.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()

        element_id = element.get("id", "")

        for strip_name in self._strip_classes:
            strip_lower = strip_name.lower()

            # Check classes
            for cls in classes:
                if strip_lower in cls.lower():
                    return True

            # Check ID
            if element_id and strip_lower in element_id.lower():
                return True

        return False


    #---------------------------------------------------------------------------
    # STAGE 3 & 4: TEXT EXTRACTION WITH DENSITY SCORING
    def _extract_text_blocks(
        self,
        soup: BeautifulSoup,
        code_element_ids: Set[int],
    ) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []

        # Heading tags
        heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

        for element in soup.find_all(True):
            # Skip if this element is part of a code block
            if id(element) in code_element_ids:
                continue

            # Skip if any ancestor is a code element
            if self._has_code_ancestor(element, code_element_ids):
                continue

            # Process headings
            if element.name in heading_tags:
                text = element.get_text(strip=True)
                if text:
                    blocks.append({
                        "type": "heading",
                        "level": int(element.name[1]),
                        "content": text,
                    })
                continue

            # Process paragraphs and text-bearing block elements
            if element.name in ("p", "article", "section", "blockquote"):
                text = element.get_text(separator=" ", strip=True)
                if not text:
                    continue

                # Apply text density scoring
                word_count = len(text.split())
                if word_count < self._min_block_words:
                    # Still include if it's a blockquote or has substantial text
                    if element.name != "blockquote" and word_count < 5:
                        continue

                density = self._compute_text_density(element)
                if density < self._min_text_density and word_count < self._min_block_words:
                    continue

                block_type = "paragraph"
                if element.name == "blockquote":
                    block_type = "blockquote"

                blocks.append({
                    "type": block_type,
                    "content": text,
                })

            # Process list items as their own blocks
            elif element.name in ("ul", "ol"):
                items = []
                for li in element.find_all("li", recursive=False):
                    li_text = li.get_text(separator=" ", strip=True)
                    if li_text:
                        items.append(li_text)

                if items:
                    list_type = "ordered_list" if element.name == "ol" else "unordered_list"
                    blocks.append({
                        "type": list_type,
                        "content": "\n".join(f"• {item}" for item in items),
                        "items": items,
                    })

        return blocks

    @staticmethod
    def _compute_text_density(element: Tag) -> float:
        """
        Compute the text-to-tag ratio for an element.
        Higher density = more likely to be real content.
        """
        text_length = len(element.get_text(strip=True))
        tag_count = len(element.find_all(True))

        # Avoid division by zero — if no child tags, density is 1.0
        if tag_count == 0:
            return 1.0

        # Include the element's own HTML length as denominator
        html_length = len(str(element))
        if html_length == 0:
            return 0.0

        return text_length / html_length

    @staticmethod
    def _has_code_ancestor(element: Tag, code_ids: Set[int]) -> bool:
        """Check if any ancestor of the element is a code block."""
        parent = element.parent
        while parent:
            if id(parent) in code_ids:
                return True
            parent = parent.parent
        return False


    #---------------------------------------------------------------------------
    # STAGE 5: POST-PROCESSING
    @staticmethod
    def _post_process(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge fragmented text blocks and clean up extracted content.
        - Merge consecutive short paragraphs that are clearly part of the same flow
        - Remove duplicate blocks
        - Clean excessive whitespace
        """
        if not blocks:
            return blocks

        processed: List[Dict[str, Any]] = []
        seen_content: Set[str] = set()

        for block in blocks:
            content = block.get("content", "")

            # Clean excessive whitespace
            content = re.sub(r"\s+", " ", content).strip()
            content = re.sub(r"\n{3,}", "\n\n", content)

            if not content:
                continue

            # Deduplicate by content
            content_key = content.lower().strip()
            if content_key in seen_content:
                continue
            seen_content.add(content_key)

            block["content"] = content

            # Try to merge with previous paragraph if both are short fragments
            if (
                block["type"] == "paragraph"
                and processed
                and processed[-1]["type"] == "paragraph"
            ):
                prev_content = processed[-1]["content"]
                prev_words = len(prev_content.split())
                curr_words = len(content.split())

                # Merge if both are short and the previous doesn't end with
                # strong punctuation
                if (
                    prev_words < 15
                    and curr_words < 15
                    and not prev_content.rstrip().endswith((".", "!", "?", ":"))
                ):
                    processed[-1]["content"] = f"{prev_content} {content}"
                    continue

            processed.append(block)

        return processed


    #---------------------------------------------------------------------------
    # STAGE 6: INTERLEAVE CODE WITH TEXT
    @staticmethod
    def _interleave_blocks(
        text_blocks: List[Dict[str, Any]],
        code_blocks: List[Dict[str, Any]],
        soup: BeautifulSoup,
    ) -> List[Dict[str, Any]]:
        if not code_blocks:
            return text_blocks

        if not text_blocks:
            return code_blocks

        # Simple strategy: distribute code blocks evenly among text blocks
        combined: List[Dict[str, Any]] = []
        total_text = len(text_blocks)
        total_code = len(code_blocks)

        code_idx = 0
        for i, text_block in enumerate(text_blocks):
            combined.append(text_block)

            # Insert code blocks at proportional positions
            while code_idx < total_code:
                # Position where this code block should appear (proportional)
                expected_text_pos = (code_idx + 1) * total_text / (total_code + 1)
                if i + 1 >= expected_text_pos:
                    combined.append(code_blocks[code_idx])
                    code_idx += 1
                else:
                    break

        # Append any remaining code blocks at the end
        while code_idx < total_code:
            combined.append(code_blocks[code_idx])
            code_idx += 1

        return combined


    #---------------------------------------------------------------------------
    # OPTIONAL DATA TARGETS
    @staticmethod
    def _extract_headers(html: str) -> List[Dict[str, Any]]:
        """Extract content from <header> elements."""
        soup = BeautifulSoup(html, "lxml")
        blocks: List[Dict[str, Any]] = []

        for header in soup.find_all("header"):
            text = header.get_text(separator=" ", strip=True)
            if text:
                blocks.append({
                    "type": "header_content",
                    "content": text,
                })

        return blocks

    @staticmethod
    def _extract_footers(html: str) -> List[Dict[str, Any]]:
        """Extract content from <footer> elements."""
        soup = BeautifulSoup(html, "lxml")
        blocks: List[Dict[str, Any]] = []

        for footer in soup.find_all("footer"):
            text = footer.get_text(separator=" ", strip=True)
            if text:
                blocks.append({
                    "type": "footer_content",
                    "content": text,
                })

        return blocks

    @staticmethod
    def _extract_ads(html: str) -> List[Dict[str, Any]]:
        """
        Extract content from elements that appear to be advertisements.
        Detected by common ad-related CSS classes and IDs.
        """
        soup = BeautifulSoup(html, "lxml")
        blocks: List[Dict[str, Any]] = []

        ad_indicators = [
            "ad", "ads", "advert", "advertisement", "banner",
            "sponsor", "promoted", "promo",
        ]

        for element in soup.find_all(True):
            classes = element.get("class", [])
            if isinstance(classes, str):
                classes = classes.split()

            element_id = element.get("id", "") or ""
            combined = " ".join(classes).lower() + " " + element_id.lower()

            is_ad = False
            for indicator in ad_indicators:
                if indicator in combined:
                    is_ad = True
                    break

            if is_ad:
                text = element.get_text(separator=" ", strip=True)
                if text and len(text) > 10:
                    blocks.append({
                        "type": "ad_content",
                        "content": text,
                    })

        return blocks

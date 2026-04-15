#======================================================================================================
# Classifies content into categories using a multi-signal approach
#======================================================================================================

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from backend.config import get_app_config
from backend.database.connection import async_session_factory
from backend.logging_config import get_logger
from backend.src.managers.database_manager import DatabaseManager

logger = get_logger("category_classifier")


class CategoryClassifier:
    """
    Classifies content into categories using a multi-signal approach
    """

    # Minimum combined score to assign a category (0.0 - 1.0)
    MIN_CONFIDENCE_THRESHOLD = 0.15

    def __init__(self) -> None:
        self._app_config = get_app_config()
        self._db_manager = DatabaseManager()

        # Load default categories from .config
        self._default_categories: Dict[str, List[str]] = (
            self._app_config.default_categories
        )

    async def classify(
        self,
        url: str,
        content_blocks: List[Dict[str, Any]],
        categories: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Classify content into the best-matching category.
        """
        # Load categories if not provided
        if categories is None:
            categories = await self._load_categories()

        if not categories:
            return None

        # Flatten content blocks into a single text blob for analysis
        full_text = self._flatten_content(content_blocks)

        if not full_text.strip():
            return None

        # Score each category
        scored: List[Tuple[Dict[str, Any], float, Dict[str, float]]] = []

        for category in categories:
            score, signals = self._score_category(url, full_text, category)
            if score > 0:
                scored.append((category, score, signals))

        if not scored:
            return None

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        best_category, best_score, best_signals = scored[0]

        # Apply minimum confidence threshold
        if best_score < self.MIN_CONFIDENCE_THRESHOLD:
            logger.info(
                "no_category_matched",
                url=url[:80],
                best_score=best_score,
                best_category=best_category.get("name", "unknown"),
            )
            return None

        result = {
            "category_id": best_category.get("id"),
            "category_name": best_category.get("name"),
            "confidence": round(best_score, 4),
            "signals": best_signals,
        }

        logger.info(
            "content_classified",
            url=url[:80],
            category=result["category_name"],
            confidence=result["confidence"],
        )

        return result

    async def classify_batch(
        self,
        items: List[Dict[str, Any]],
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Classify multiple items efficiently by loading categories once.

        Args:
            items: List of dicts with "url" and "content_blocks" keys.

        Returns:
            List of classification results (same order as input).
        """
        categories = await self._load_categories()
        results = []

        for item in items:
            result = await self.classify(
                url=item["url"],
                content_blocks=item["content_blocks"],
                categories=categories,
            )
            results.append(result)

        return results


    #---------------------------------------------------------------------------
    # SCORING
    def _score_category(
        self,
        url: str,
        text: str,
        category: Dict[str, Any],
    ) -> Tuple[float, Dict[str, float]]:
        """
        Score how well content matches a category using multiple signals.
        Returns (total_score, signal_breakdown).
        """
        signals: Dict[str, float] = {}

        # Signal 1: URL pattern matching (weight: 0.3)
        url_score = self._score_url_patterns(url, category)
        signals["url_pattern"] = url_score

        # Signal 2: Keyword frequency (weight: 0.5)
        keyword_score = self._score_keywords(text, category)
        signals["keyword_frequency"] = keyword_score

        # Signal 3: Domain matching (weight: 0.2)
        domain_score = self._score_domain(url, category)
        signals["domain_match"] = domain_score

        # Weighted combination
        total = (url_score * 0.3) + (keyword_score * 0.5) + (domain_score * 0.2)

        return total, signals

    @staticmethod
    def _score_url_patterns(url: str, category: Dict[str, Any]) -> float:
        """
        Score based on URL pattern matching.
        Returns 1.0 if any pattern matches, 0.0 otherwise.
        """
        url_patterns = category.get("url_patterns", [])
        if not url_patterns:
            return 0.0

        url_lower = url.lower()

        for pattern in url_patterns:
            rule_type = pattern.get("type", "").lower()
            value = pattern.get("pattern", "").lower()

            if not rule_type or not value:
                continue

            if rule_type == "contains" and value in url_lower:
                return 1.0
            elif rule_type == "starts_with" and url_lower.startswith(value):
                return 1.0
            elif rule_type == "ends_with" and url_lower.endswith(value):
                return 1.0
            elif rule_type == "domain":
                parsed = urlparse(url_lower)
                domain = parsed.netloc.split(":")[0]
                if domain == value or domain.endswith(f".{value}"):
                    return 1.0
            elif rule_type == "regex":
                try:
                    if re.search(value, url_lower):
                        return 1.0
                except re.error:
                    pass

        return 0.0

    @staticmethod
    def _score_keywords(text: str, category: Dict[str, Any]) -> float:
        """
        Score based on keyword frequency in the content text.
        Returns a normalized score between 0.0 and 1.0.
        """
        keywords = category.get("keywords", [])
        if not keywords:
            return 0.0

        text_lower = text.lower()
        words = text_lower.split()
        total_words = len(words)

        if total_words == 0:
            return 0.0

        # Count keyword occurrences
        match_count = 0
        matched_keywords = set()

        for keyword in keywords:
            keyword_lower = keyword.lower()

            # Count occurrences of this keyword (as whole word or phrase)
            if " " in keyword_lower:
                # Multi-word keyword — search in full text
                occurrences = text_lower.count(keyword_lower)
            else:
                # Single-word keyword — count in word list
                occurrences = words.count(keyword_lower)

            if occurrences > 0:
                match_count += occurrences
                matched_keywords.add(keyword_lower)

        if match_count == 0:
            return 0.0

        # Score components:
        #   keyword_coverage: fraction of category keywords found
        #   density: keyword matches per 100 words (capped at 1.0)
        keyword_coverage = len(matched_keywords) / len(keywords)
        density = min(match_count / (total_words / 100), 1.0)

        # Combined: weight coverage higher than raw density
        score = (keyword_coverage * 0.7) + (density * 0.3)

        return min(score, 1.0)

    @staticmethod
    def _score_domain(url: str, category: Dict[str, Any]) -> float:
        """
        Score based on the domain of the URL.
        Checks if the domain or its parts match category keywords.
        """
        keywords = category.get("keywords", [])
        if not keywords:
            return 0.0

        parsed = urlparse(url.lower())
        domain = parsed.netloc.split(":")[0]

        # Split domain into parts (e.g., "tech.example.com" -> ["tech", "example", "com"])
        domain_parts = domain.replace(".", " ").replace("-", " ").split()

        for keyword in keywords:
            keyword_lower = keyword.lower()
            for part in domain_parts:
                if keyword_lower == part or keyword_lower in part:
                    return 1.0

        return 0.0


    #---------------------------------------------------------------------------
    # DATA LOADING
    async def _load_categories(self) -> List[Dict[str, Any]]:
        """
        Load categories from the database, supplemented by defaults from .config.
        Returns a unified list of category dicts.
        """
        categories: List[Dict[str, Any]] = []

        # Load from database
        try:
            async with async_session_factory() as session:
                db_categories = await self._db_manager.list_categories(
                    session, active_only=True
                )
                for cat in db_categories:
                    categories.append({
                        "id": cat.id,
                        "name": cat.name,
                        "keywords": cat.keywords or [],
                        "url_patterns": cat.url_patterns or [],
                    })
        except Exception as exc:
            logger.warning("failed_to_load_db_categories", error=str(exc))

        # Supplement with .config defaults (only add if not already in DB)
        db_names = {c["name"].lower() for c in categories}

        for name, keywords in self._default_categories.items():
            if name.lower() not in db_names:
                categories.append({
                    "id": None,
                    "name": name,
                    "keywords": keywords,
                    "url_patterns": [],
                })

        return categories


    #---------------------------------------------------------------------------
    # HELPERS
    @staticmethod
    def _flatten_content(content_blocks: List[Dict[str, Any]]) -> str:
        """Concatenate all content block text into a single string."""
        parts: List[str] = []
        for block in content_blocks:
            content = block.get("content", "")
            if content:
                parts.append(content)
        return " ".join(parts)





# OTHER CODE, KEEPING FOR REFENRCE (so I don't forget)


# =============================================================================
# OPTIONAL ML EXTENSION
# =============================================================================
# To enable ML-based classification:
#   1. Uncomment fasttext-wheel in requirements.txt
#   2. Set USE_ML_CLASSIFIER=true in .env
#   3. Place a trained fastText model at /WebScraper/models/classifier.bin
#
# The ML classifier runs as a secondary signal alongside rule-based scoring.
# Per spec, it is only used if inference latency stays under 100ms per page.
#
# class MLClassifier:
#     """fastText-based text classifier for category prediction."""
#
#     def __init__(self, model_path: str = "/WebScraper/models/classifier.bin"):
#         import fasttext
#         self._model = fasttext.load_model(model_path)
#
#     def predict(self, text: str) -> Tuple[str, float]:
#         """Predict category with confidence score."""
#         labels, scores = self._model.predict(text, k=1)
#         label = labels[0].replace("__label__", "")
#         confidence = float(scores[0])
#         return label, confidence
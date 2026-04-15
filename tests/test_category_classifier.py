#======================================================================================================
# Tests for the rule-based category classifier.
#======================================================================================================

from __future__ import annotations

import pytest

from backend.src.managers.category_classifier import CategoryClassifier


@pytest.fixture
def classifier() -> CategoryClassifier:
    return CategoryClassifier()


class TestCategoryClassifier:

    def test_score_keywords_high_match(self, classifier: CategoryClassifier):
        """Text with many matching keywords gets a high score."""
        category = {
            "keywords": ["python", "programming", "developer", "software"],
            "url_patterns": [],
        }
        text = (
            "Python is a great programming language for software developers. "
            "Many developer tools are built with Python programming frameworks."
        )

        score = classifier._score_keywords(text, category)
        assert score > 0.3

    def test_score_keywords_no_match(self, classifier: CategoryClassifier):
        """Text with no matching keywords gets a zero score."""
        category = {
            "keywords": ["football", "basketball", "soccer"],
            "url_patterns": [],
        }
        text = "The weather today is sunny and warm with clear skies."

        score = classifier._score_keywords(text, category)
        assert score == 0.0

    def test_score_keywords_empty_text(self, classifier: CategoryClassifier):
        """Empty text returns zero score."""
        category = {"keywords": ["test"], "url_patterns": []}
        assert classifier._score_keywords("", category) == 0.0

    def test_score_keywords_empty_keywords(self, classifier: CategoryClassifier):
        """No keywords defined returns zero score."""
        category = {"keywords": [], "url_patterns": []}
        assert classifier._score_keywords("some text here", category) == 0.0

    def test_score_url_patterns_contains(self, classifier: CategoryClassifier):
        """URL matching a 'contains' pattern scores 1.0."""
        category = {
            "keywords": [],
            "url_patterns": [{"type": "contains", "pattern": "/tech/"}],
        }
        assert classifier._score_url_patterns("https://example.com/tech/article", category) == 1.0
        assert classifier._score_url_patterns("https://example.com/sports/game", category) == 0.0

    def test_score_url_patterns_starts_with(self, classifier: CategoryClassifier):
        """URL matching a 'starts_with' pattern scores 1.0."""
        category = {
            "keywords": [],
            "url_patterns": [{"type": "starts_with", "pattern": "https://blog.example"}],
        }
        assert classifier._score_url_patterns("https://blog.example.com/post", category) == 1.0
        assert classifier._score_url_patterns("https://shop.example.com/item", category) == 0.0

    def test_score_url_patterns_domain(self, classifier: CategoryClassifier):
        """URL matching a 'domain' pattern scores 1.0."""
        category = {
            "keywords": [],
            "url_patterns": [{"type": "domain", "pattern": "techcrunch.com"}],
        }
        assert classifier._score_url_patterns("https://techcrunch.com/article", category) == 1.0
        assert classifier._score_url_patterns("https://cnn.com/article", category) == 0.0

    def test_score_url_patterns_no_patterns(self, classifier: CategoryClassifier):
        """No URL patterns returns zero."""
        category = {"keywords": [], "url_patterns": []}
        assert classifier._score_url_patterns("https://example.com", category) == 0.0

    def test_score_domain_matching(self, classifier: CategoryClassifier):
        """Domain parts matching keywords scores 1.0."""
        category = {"keywords": ["tech", "dev"], "url_patterns": []}
        assert classifier._score_domain("https://tech.example.com/page", category) == 1.0
        assert classifier._score_domain("https://sports.example.com/page", category) == 0.0

    def test_flatten_content(self, classifier: CategoryClassifier):
        """Content blocks are flattened into a single string."""
        blocks = [
            {"type": "heading", "content": "Title"},
            {"type": "paragraph", "content": "Body text here."},
            {"type": "code_block", "content": "print('hello')"},
        ]
        result = classifier._flatten_content(blocks)
        assert "Title" in result
        assert "Body text here." in result
        assert "print('hello')" in result

    def test_score_category_combined(self, classifier: CategoryClassifier):
        """Combined scoring weights all three signals."""
        category = {
            "keywords": ["python", "programming"],
            "url_patterns": [{"type": "contains", "pattern": "dev"}],
        }

        score, signals = classifier._score_category(
            url="https://dev.to/article",
            text="Python programming is awesome for building developer tools.",
            category=category,
        )

        assert score > 0
        assert "url_pattern" in signals
        assert "keyword_frequency" in signals
        assert "domain_match" in signals

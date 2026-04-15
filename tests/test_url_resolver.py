#======================================================================================================
# Tests for URL discovery, normalization, and filtering.
#======================================================================================================

from __future__ import annotations

import pytest

from backend.src.services.url_resolver import URLResolver


@pytest.fixture
def resolver() -> URLResolver:
    return URLResolver()


class TestURLResolver:

    def test_normalize_relative_url(self, resolver: URLResolver):
        """Relative URLs are resolved against the base URL."""
        result = resolver.normalize_url("/page2", "https://example.com/page1")
        assert result == "https://example.com/page2"

    def test_normalize_strips_fragment(self, resolver: URLResolver):
        """Fragments are removed from URLs."""
        result = resolver.normalize_url("https://example.com/page#section", "https://example.com")
        assert "#" not in result

    def test_normalize_strips_trailing_slash(self, resolver: URLResolver):
        """Trailing slashes are normalized."""
        result = resolver.normalize_url("https://example.com/page/", "https://example.com")
        assert result == "https://example.com/page"

    def test_normalize_lowercases_domain(self, resolver: URLResolver):
        """Domains are lowercased."""
        result = resolver.normalize_url("https://EXAMPLE.COM/Page", "https://example.com")
        assert "example.com" in result

    def test_normalize_skips_javascript(self, resolver: URLResolver):
        """JavaScript URLs return None."""
        result = resolver.normalize_url("javascript:void(0)", "https://example.com")
        assert result is None

    def test_normalize_skips_mailto(self, resolver: URLResolver):
        """Mailto URLs return None."""
        result = resolver.normalize_url("mailto:test@example.com", "https://example.com")
        assert result is None

    def test_extract_links(self, resolver: URLResolver):
        """Extracts valid links from HTML."""
        html = """
        <html><body>
            <a href="/page1">Page 1</a>
            <a href="https://example.com/page2">Page 2</a>
            <a href="javascript:void(0)">Bad</a>
            <a href="mailto:test@test.com">Mail</a>
        </body></html>
        """
        links = resolver.extract_links(html, "https://example.com")

        assert len(links) == 2
        assert "https://example.com/page1" in links
        assert "https://example.com/page2" in links

    def test_extract_links_deduplicates(self, resolver: URLResolver):
        """Duplicate links are removed."""
        html = """
        <html><body>
            <a href="/page1">Link 1</a>
            <a href="/page1">Link 1 again</a>
        </body></html>
        """
        links = resolver.extract_links(html, "https://example.com")
        assert len(links) == 1

    def test_extract_links_respects_seen_urls(self, resolver: URLResolver):
        """Already-seen URLs are excluded."""
        html = '<html><body><a href="/page1">Link</a></body></html>'
        seen = {"https://example.com/page1"}
        links = resolver.extract_links(html, "https://example.com", seen_urls=seen)
        assert len(links) == 0

    def test_extract_links_with_rules(self, resolver: URLResolver):
        """URL rules filter discovered links."""
        html = """
        <html><body>
            <a href="/blog/post1">Blog</a>
            <a href="/about">About</a>
            <a href="/blog/post2">Blog 2</a>
        </body></html>
        """
        rules = [{"type": "contains", "pattern": "/blog/"}]
        links = resolver.extract_links(html, "https://example.com", url_rules=rules)

        assert len(links) == 2
        assert all("/blog/" in link for link in links)

    def test_rule_contains(self, resolver: URLResolver):
        """Contains rule matches URLs with the pattern."""
        rules = [{"type": "contains", "pattern": "blog"}]
        assert resolver.matches_rules("https://example.com/blog/post1", rules) is True
        assert resolver.matches_rules("https://example.com/about", rules) is False

    def test_rule_starts_with(self, resolver: URLResolver):
        """Starts_with rule matches URL prefix."""
        rules = [{"type": "starts_with", "pattern": "https://example.com/docs"}]
        assert resolver.matches_rules("https://example.com/docs/api", rules) is True
        assert resolver.matches_rules("https://example.com/blog", rules) is False

    def test_rule_ends_with(self, resolver: URLResolver):
        """Ends_with rule matches URL suffix."""
        rules = [{"type": "ends_with", "pattern": ".html"}]
        assert resolver.matches_rules("https://example.com/page.html", rules) is True
        assert resolver.matches_rules("https://example.com/page.php", rules) is False

    def test_rule_domain(self, resolver: URLResolver):
        """Domain rule matches the URL's domain."""
        rules = [{"type": "domain", "pattern": "example.com"}]
        assert resolver.matches_rules("https://example.com/page", rules) is True
        assert resolver.matches_rules("https://other.com/page", rules) is False

    def test_rule_regex(self, resolver: URLResolver):
        """Regex rule matches using regular expressions."""
        rules = [{"type": "regex", "pattern": r"/post/\d+"}]
        assert resolver.matches_rules("https://example.com/post/123", rules) is True
        assert resolver.matches_rules("https://example.com/post/abc", rules) is False

    def test_get_domain(self, resolver: URLResolver):
        """Domain extraction works correctly."""
        assert resolver.get_domain("https://www.example.com/page") == "www.example.com"
        assert resolver.get_domain("https://example.com:8080/page") == "example.com"

    def test_is_same_domain(self, resolver: URLResolver):
        """Same-domain check works correctly."""
        assert resolver.is_same_domain(
            "https://example.com/page1",
            "https://example.com/page2"
        ) is True
        assert resolver.is_same_domain(
            "https://example.com/page1",
            "https://other.com/page2"
        ) is False

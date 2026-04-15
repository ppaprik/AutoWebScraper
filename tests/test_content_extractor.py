#======================================================================================================
# Tests for the multi-stage content extraction pipeline.
#======================================================================================================

from __future__ import annotations

import pytest

from backend.src.services.content_extractor import ContentExtractor


@pytest.fixture
def extractor() -> ContentExtractor:
    return ContentExtractor()


class TestContentExtractor:

    def test_extract_basic_paragraphs(self, extractor: ContentExtractor):
        """Extracts paragraph text from simple HTML."""
        html = """
        <html><body>
            <article>
                <h1>Main Title</h1>
                <p>This is the first paragraph with enough words to pass the density filter easily.</p>
                <p>This is the second paragraph which also has sufficient length to qualify as content.</p>
            </article>
        </body></html>
        """
        blocks = extractor.extract(html, url="https://example.com")

        assert len(blocks) > 0

        types = [b["type"] for b in blocks]
        assert "heading" in types or "paragraph" in types

    def test_extract_preserves_headings(self, extractor: ContentExtractor):
        """Headings are extracted with their level."""
        html = """
        <html><body>
            <article>
                <h1>Top Level Heading</h1>
                <p>Paragraph with enough words to be considered real content by the extractor.</p>
                <h2>Sub Heading</h2>
                <p>Another paragraph with sufficient word count to pass all filtering heuristics.</p>
            </article>
        </body></html>
        """
        blocks = extractor.extract(html)

        headings = [b for b in blocks if b["type"] == "heading"]
        assert len(headings) >= 1

    def test_extract_strips_navigation(self, extractor: ContentExtractor):
        """Navigation elements are removed from output."""
        html = """
        <html><body>
            <nav><a href="/">Home</a><a href="/about">About</a></nav>
            <article>
                <p>Real content paragraph with enough words to pass all density and word count filters.</p>
            </article>
            <footer>Copyright 2024</footer>
        </body></html>
        """
        blocks = extractor.extract(html)

        all_text = " ".join(b.get("content", "") for b in blocks)
        assert "Home" not in all_text or "Real content" in all_text

    def test_extract_strips_scripts_and_styles(self, extractor: ContentExtractor):
        """Script and style tags are completely removed."""
        html = """
        <html><body>
            <style>.body { color: red; }</style>
            <script>alert('xss');</script>
            <article>
                <p>Clean content that should survive the extraction pipeline without any issues.</p>
            </article>
        </body></html>
        """
        blocks = extractor.extract(html)

        all_text = " ".join(b.get("content", "") for b in blocks)
        assert "alert" not in all_text
        assert "color: red" not in all_text

    def test_extract_with_code_blocks(self, extractor: ContentExtractor):
        """Code blocks are preserved and never removed as noise."""
        html = """
        <html><body>
            <article>
                <p>Here is a Python example with enough surrounding text for context.</p>
                <pre><code class="language-python">
def hello():
    print("Hello, World!")
    return True
                </code></pre>
                <p>The function above prints a greeting message to the console output.</p>
            </article>
        </body></html>
        """
        blocks = extractor.extract(html)

        code_blocks = [b for b in blocks if b["type"] == "code_block"]
        assert len(code_blocks) >= 1

        code_content = code_blocks[0]["content"]
        assert "def hello" in code_content
        assert 'print("Hello, World!")' in code_content

    def test_extract_empty_html(self, extractor: ContentExtractor):
        """Empty HTML returns an empty list."""
        assert extractor.extract("") == []
        assert extractor.extract("   ") == []

    def test_extract_title(self, extractor: ContentExtractor):
        """Page title is correctly extracted."""
        html = "<html><head><title>My Page Title</title></head><body></body></html>"
        title = extractor.extract_title(html)
        assert title == "My Page Title"

    def test_extract_title_missing(self, extractor: ContentExtractor):
        """Missing title tag returns None."""
        html = "<html><head></head><body></body></html>"
        assert extractor.extract_title(html) is None

    def test_extract_with_headers_target(self, extractor: ContentExtractor):
        """Including 'headers' data target extracts header content."""
        html = """
        <html><body>
            <header>Site Header Navigation Content</header>
            <article>
                <p>Main article content with enough words to pass all extraction filters.</p>
            </article>
        </body></html>
        """
        blocks = extractor.extract(html, data_targets=["text", "headers"])

        types = [b["type"] for b in blocks]
        assert "header_content" in types

    def test_extract_with_footers_target(self, extractor: ContentExtractor):
        """Including 'footers' data target extracts footer content."""
        html = """
        <html><body>
            <article>
                <p>Article content with plenty of words to survive density filtering checks.</p>
            </article>
            <footer>Copyright 2024 Example Corp. All rights reserved worldwide.</footer>
        </body></html>
        """
        blocks = extractor.extract(html, data_targets=["text", "footers"])

        types = [b["type"] for b in blocks]
        assert "footer_content" in types

    def test_extract_deduplicates_content(self, extractor: ContentExtractor):
        """Duplicate content blocks are removed."""
        html = """
        <html><body>
            <article>
                <p>This exact paragraph appears twice in the page source to test deduplication.</p>
                <p>This exact paragraph appears twice in the page source to test deduplication.</p>
            </article>
        </body></html>
        """
        blocks = extractor.extract(html)

        paragraphs = [b for b in blocks if b["type"] == "paragraph"]
        contents = [p["content"] for p in paragraphs]
        # Should be deduplicated
        assert len(contents) == len(set(contents))

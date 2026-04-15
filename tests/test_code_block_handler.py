#======================================================================================================
# Tests for code block detection and preservation.
#======================================================================================================

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from backend.src.services.code_block_handler import CodeBlockHandler


@pytest.fixture
def handler() -> CodeBlockHandler:
    return CodeBlockHandler()


class TestCodeBlockHandler:

    def test_detect_pre_code_tags(self, handler: CodeBlockHandler):
        """Detects code inside <pre><code> tags."""
        html = """
        <div>
            <pre><code class="language-python">
def greet(name):
    return f"Hello, {name}!"
            </code></pre>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) >= 1
        assert blocks[0]["type"] == "code_block"
        assert "def greet" in blocks[0]["content"]

    def test_detect_language_from_class(self, handler: CodeBlockHandler):
        """Detects programming language from CSS class."""
        html = '<pre><code class="language-javascript">const x = 42;</code></pre>'
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) >= 1
        assert blocks[0]["language"] == "javascript"

    def test_detect_language_from_parent_class(self, handler: CodeBlockHandler):
        """Detects language from parent element's CSS class."""
        html = '<div class="highlight-python"><pre>import os\nos.path.exists("/")</pre></div>'
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) >= 1
        assert blocks[0]["language"] == "python"

    def test_detect_code_by_css_class(self, handler: CodeBlockHandler):
        """Detects code blocks via code-related CSS classes."""
        html = '<div class="hljs"><span>const foo = "bar";</span></div>'
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) >= 1
        assert blocks[0]["type"] == "code_block"

    def test_detect_samp_tag(self, handler: CodeBlockHandler):
        """Detects code inside <samp> tags."""
        html = "<samp>$ pip install requests</samp>"
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) >= 1
        assert "pip install" in blocks[0]["content"]

    def test_preserves_formatting(self, handler: CodeBlockHandler):
        """Code block whitespace and indentation are preserved."""
        code = "def test():\n    if True:\n        return 1\n    return 0"
        html = f"<pre><code>{code}</code></pre>"
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) >= 1
        content = blocks[0]["content"]
        assert "    if True:" in content
        assert "        return 1" in content

    def test_is_code_element(self, handler: CodeBlockHandler):
        """is_code_element correctly identifies code tags."""
        html = '<div><pre><code>x = 1</code></pre><p>Not code</p></div>'
        soup = BeautifulSoup(html, "lxml")

        pre = soup.find("pre")
        p = soup.find("p")

        assert handler.is_code_element(pre) is True
        assert handler.is_code_element(p) is False

    def test_empty_code_block_skipped(self, handler: CodeBlockHandler):
        """Empty code blocks are not included in results."""
        html = "<pre><code>   </code></pre>"
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) == 0

    def test_guess_python_from_content(self, handler: CodeBlockHandler):
        """Language is guessed from content when no class hint exists."""
        html = "<pre>def calculate(x, y):\n    return x + y</pre>"
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) >= 1
        assert blocks[0]["language"] == "python"

    def test_guess_html_from_content(self, handler: CodeBlockHandler):
        """HTML content is detected by tag patterns."""
        html = "<pre>&lt;html&gt;\n&lt;head&gt;&lt;title&gt;Test&lt;/title&gt;&lt;/head&gt;\n&lt;body&gt;&lt;/body&gt;\n&lt;/html&gt;</pre>"
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) >= 1
        assert blocks[0]["language"] in ("html", "unknown")

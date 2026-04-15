# Scraping Rules Reference

This document covers URL filtering rules, crawl modes, content extraction configuration, code block handling, and content versioning behavior.

---

## Crawl Modes

### Single

Scrapes exactly one page. No link discovery or following.

- **Use when:** you need content from a specific URL
- **URL rules:** ignored
- **Limits:** none (one page only)

### Rule-Based

Starts from the given URL, discovers links on each page, and follows only those matching your URL rules.

- **Use when:** you want to scrape a specific section of a site (e.g., all blog posts)
- **URL rules:** required — only matching links are followed
- **Limits:** `max_pages_per_job` from `.config`

### Infinite

Starts from the given URL and follows all discovered links on the same domain. Respects depth and page count limits.

- **Use when:** you want to crawl an entire site
- **URL rules:** ignored (all same-domain links are followed)
- **Limits:** `max_pages_per_job` and `max_crawl_depth` from `.config`

### Category

Like Rule-Based, but uses the URL patterns defined on the assigned category instead of (or in addition to) manually specified rules.

- **Use when:** you have a category with URL patterns and want to scrape matching pages
- **URL rules:** loaded from the category's `url_patterns` field
- **Limits:** `max_pages_per_job` from `.config`

---

## URL Rules

URL rules control which discovered links the scraper will follow. Each rule has a `type` and a `pattern`. A link is followed if it matches **at least one** rule.

### Rule Types

| Type | Behavior | Example Pattern | Matches |
|------|----------|-----------------|---------|
| `contains` | URL contains the pattern string | `/blog/` | `https://example.com/blog/post-1` |
| `starts_with` | URL starts with the pattern | `https://docs.example.com` | `https://docs.example.com/api/v1` |
| `ends_with` | URL ends with the pattern | `.html` | `https://example.com/page.html` |
| `domain` | URL's domain matches the pattern | `example.com` | `https://example.com/any-path` |
| `regex` | URL matches the regular expression | `/post/\d+` | `https://example.com/post/42` |

### Rule Format

Rules are specified as JSON objects:

```json
[
  {"type": "contains", "pattern": "/blog/"},
  {"type": "domain", "pattern": "docs.example.com"},
  {"type": "ends_with", "pattern": ".html"}
]
```

All matching is case-insensitive. For `domain` rules, subdomains are matched (e.g., pattern `example.com` matches `api.example.com`).

### Blocked Domains

Domains listed in `.config` under `[scraper] blocked_domains` are never scraped regardless of rules. Default blocked domains: `facebook.com`, `instagram.com`, `twitter.com`, `x.com`.

### Skipped Extensions

URLs ending with file extensions listed in `.config` under `[scraper] skip_extensions` are never followed. Defaults include `.pdf`, `.jpg`, `.png`, `.mp4`, `.zip`, etc.

---

## Data Targets

Each job can specify which parts of a page to extract. Multiple targets can be combined.

| Target | Description |
|--------|-------------|
| `text` | Main content: headings, paragraphs, lists, blockquotes, code blocks. Default. |
| `headers` | Content from `<header>` elements (site headers, navigation). |
| `footers` | Content from `<footer>` elements (copyright, links). |
| `ads` | Content from elements with ad-related CSS classes or IDs. |

Default is `["text"]` if not specified.

---

## Content Extraction

### Pipeline Stages

1. **Readability** — the readability-lxml algorithm identifies the main content area, stripping boilerplate.

2. **DOM Filtering** — removes elements by:
   - Tag name: `nav`, `footer`, `header`, `aside`, `script`, `style`, `noscript`, `iframe` (configurable in `.config`)
   - CSS class/ID: `sidebar`, `advertisement`, `ad-container`, `social-share`, `cookie-banner`, `popup` (configurable)
   - Inline style: elements with `display:none` or `visibility:hidden`
   - HTML comments

3. **Code Block Detection** — runs before text filtering to ensure code is never removed. See Code Block Handling below.

4. **Text Density Scoring** — each text block is scored by its text-to-tag ratio. Blocks below `min_text_density` (default 0.25) with fewer than `min_block_words` (default 20) words are filtered out.

5. **Post-Processing** — merges short consecutive paragraphs that are fragments of the same sentence, removes exact duplicates, and normalizes whitespace.

6. **Interleaving** — text blocks and code blocks are combined in approximate document order.

### Output Format

Extraction produces a JSON array of typed content blocks:

```json
[
  {"type": "heading", "level": 1, "content": "Article Title"},
  {"type": "paragraph", "content": "Article body text..."},
  {"type": "code_block", "language": "python", "content": "def hello():\n    print('hi')"},
  {"type": "blockquote", "content": "A quoted passage..."},
  {"type": "unordered_list", "content": "• Item 1\n• Item 2", "items": ["Item 1", "Item 2"]},
  {"type": "ordered_list", "content": "• Step 1\n• Step 2", "items": ["Step 1", "Step 2"]}
]
```

Additional block types when non-default data targets are enabled:

- `header_content` — from `<header>` elements
- `footer_content` — from `<footer>` elements
- `ad_content` — from ad-related elements

---

## Code Block Handling

Code is detected through three methods, applied in order:

### 1. HTML Tags

Elements using `<pre>`, `<code>`, `<samp>`, or `<kbd>` tags are always treated as code.

### 2. CSS Class Hints

Elements with CSS classes containing any of these patterns are treated as code: `highlight`, `code`, `syntax`, `prism`, `hljs`, `codehilite`, `sourceCode`, `listing`, `mono`, `monospace`, `console`, `terminal`, `shell`, `bash`, `language-*`, `lang-*`.

Elements with inline styles containing `monospace` or `courier` font families are also detected.

### 3. Symbol Density Analysis

For elements without explicit code tags or classes, the handler counts code-characteristic symbols (`{ } [ ] ; = => // /* */ ( ) < > :: -> | & % #`) and compares to total character count. If the ratio exceeds `min_symbol_density` (default 0.08), the block is treated as code.

A secondary check looks for consistent indentation patterns (lines starting with 2+ spaces or tabs). Blocks with moderate symbol density AND high indentation ratio are also treated as code.

### Preservation Rules

- Code is **never removed** as noise, regardless of its text density score
- Exact formatting is preserved: indentation, line breaks, whitespace
- Code blocks include a `language` field detected from CSS classes, `data-language` attributes, or content heuristics (Python, JavaScript, HTML, CSS, SQL, Bash, JSON, and 30+ other languages)

---

## Content Versioning

Scraped content is versioned using a git-like model that avoids storing duplicate data.

### How It Works

1. **First scrape** of a URL creates a **snapshot** — the full content is stored in `full_content`.

2. On **subsequent scrapes**, the new content's SHA-256 hash is compared to the previous version's hash.

3. If the hash **matches** (content unchanged), a version entry is created with an empty diff and `change_summary: "No changes detected"`.

4. If the hash **differs**, a structured diff is computed and stored in `diff_content`:

```json
{
  "added": [{"type": "paragraph", "content": "New text"}],
  "removed": [{"type": "paragraph", "content": "Old text"}],
  "modified": [
    {
      "index": 2,
      "old": {"type": "heading", "content": "Old Title"},
      "new": {"type": "heading", "content": "Updated Title"}
    }
  ]
}
```

### Reconstructing Content

Any version can be reconstructed by:

1. Finding the nearest snapshot (where `is_snapshot = true`)
2. Applying each subsequent diff in order up to the target version

This is handled automatically by the `DatabaseManager._reconstruct_content()` method.

### Storage Efficiency

For pages that change minimally between scrapes (e.g., a news article with an updated timestamp), only the changed blocks are stored. A 10KB article that changes one paragraph stores approximately 200 bytes instead of duplicating the full 10KB.

---

## Rate Limiting and Politeness

The scraper respects target servers through several mechanisms:

- **Request delay:** configurable pause between requests (`SCRAPER_DEFAULT_DELAY_BETWEEN_REQUESTS`, default 1.0 seconds)
- **Concurrency limit:** maximum parallel requests per worker (`SCRAPER_MAX_CONCURRENT_REQUESTS`, default 10)
- **Retry backoff:** failed requests retry with increasing delays (`retry_delay * attempt_number`)
- **Timeout:** requests that exceed `SCRAPER_DEFAULT_TIMEOUT` (default 30 seconds) are abandoned
- **Blocked domains:** domains in the block list are never contacted

---

## Job Lifecycle

```
PENDING → RUNNING → COMPLETED
                  → FAILED
                  → STOPPED (user-initiated)
         RUNNING → PAUSED → RUNNING (resumed)
                          → STOPPED (user-initiated)
```

- **PENDING:** job is queued in Celery, waiting for a worker
- **RUNNING:** worker is actively scraping pages
- **PAUSED:** worker is blocked, waiting for a resume signal (cookies and state are preserved)
- **COMPLETED:** all pages scraped successfully (or all discoverable pages exhausted)
- **FAILED:** unrecoverable error or all pages failed
- **STOPPED:** user clicked Stop or the job was cancelled

Pause, resume, and stop signals are transmitted via Redis flags that the scraper polls between page fetches. This ensures graceful shutdown without data loss.
